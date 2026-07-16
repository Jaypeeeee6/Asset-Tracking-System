"""Helpers for asset supporting-document uploads."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename

ALLOWED_DOCUMENT_EXTENSIONS = frozenset({
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'zip',
})
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_DOCUMENTS_PER_UPLOAD = 20


def get_documents_root():
    root = Path(__file__).resolve().parent.parent / 'uploads' / 'asset_documents'
    root.mkdir(parents=True, exist_ok=True)
    return root


def allowed_document_filename(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower()
    return ext in ALLOWED_DOCUMENT_EXTENSIONS


def document_path(stored_filename):
    return get_documents_root() / stored_filename


def delete_document_file(stored_filename):
    if not stored_filename:
        return
    path = document_path(stored_filename)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _migrate_asset_documents(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            content_type TEXT,
            file_size INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE
        )
    ''')
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_asset_documents_asset_id '
        'ON asset_documents(asset_id)'
    )


def list_documents_for_asset(cur, asset_id):
    cur.execute(
        '''
        SELECT id, asset_id, original_filename, stored_filename, content_type, file_size, created_at
        FROM asset_documents
        WHERE asset_id = ?
        ORDER BY created_at, id
        ''',
        (asset_id,),
    )
    rows = cur.fetchall()
    result = []
    for row in rows:
        result.append({
            'id': row[0],
            'asset_id': row[1],
            'original_filename': row[2],
            'stored_filename': row[3],
            'content_type': row[4],
            'file_size': row[5] or 0,
            'created_at': row[6],
            'download_url': f'/assets/{asset_id}/documents/{row[0]}/download',
        })
    return result


def save_uploaded_file_for_asset(cur, asset_id, file_storage):
    """
    Persist one uploaded file for an asset.
    Returns (doc_dict, None) on success, (None, None) if empty, or (None, error) on failure.
    """
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None, None
    original = (file_storage.filename or '').strip()
    if not original:
        return None, None
    if not allowed_document_filename(original):
        return None, f'File type not allowed: {original}'

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_DOCUMENT_BYTES:
        return None, f'File too large (max 10 MB): {original}'

    safe_base = secure_filename(original) or 'document'
    ext = ''
    if '.' in safe_base:
        ext = '.' + safe_base.rsplit('.', 1)[-1].lower()
    stored = f'{asset_id}_{uuid.uuid4().hex}{ext}'
    dest = document_path(stored)
    file_storage.save(str(dest))
    content_type = getattr(file_storage, 'content_type', None) or 'application/octet-stream'

    cur.execute(
        '''
        INSERT INTO asset_documents
            (asset_id, original_filename, stored_filename, content_type, file_size)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (asset_id, original, stored, content_type, size),
    )
    doc_id = cur.lastrowid
    return {
        'id': doc_id,
        'asset_id': asset_id,
        'original_filename': original,
        'stored_filename': stored,
        'content_type': content_type,
        'file_size': size,
        'download_url': f'/assets/{asset_id}/documents/{doc_id}/download',
    }, None


def save_uploaded_files_for_assets(cur, asset_ids, file_storages):
    """
    Save each upload once, then copy the stored file to every other asset id.
    Returns (saved_count, error_message).
    """
    asset_ids = [int(a) for a in asset_ids if a is not None]
    if not asset_ids:
        return 0, None
    files = [
        f for f in (file_storages or [])
        if f and getattr(f, 'filename', None) and str(f.filename).strip()
    ]
    if not files:
        return 0, None
    if len(files) > MAX_DOCUMENTS_PER_UPLOAD:
        return 0, f'You can upload at most {MAX_DOCUMENTS_PER_UPLOAD} files at once.'

    saved = 0
    first_id = asset_ids[0]
    for file_storage in files:
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        first_doc, err = save_uploaded_file_for_asset(cur, first_id, file_storage)
        if err:
            return saved, err
        if not first_doc:
            continue
        saved += 1
        src = document_path(first_doc['stored_filename'])
        for other_id in asset_ids[1:]:
            ext = Path(first_doc['stored_filename']).suffix
            stored = f'{other_id}_{uuid.uuid4().hex}{ext}'
            dest = document_path(stored)
            try:
                dest.write_bytes(src.read_bytes())
            except OSError as exc:
                return saved, f'Failed to copy document: {exc}'
            cur.execute(
                '''
                INSERT INTO asset_documents
                    (asset_id, original_filename, stored_filename, content_type, file_size)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    other_id,
                    first_doc['original_filename'],
                    stored,
                    first_doc['content_type'],
                    first_doc['file_size'],
                ),
            )
            saved += 1
    return saved, None


def delete_document_record(cur, asset_id, document_id):
    cur.execute(
        'SELECT id, stored_filename FROM asset_documents WHERE id = ? AND asset_id = ?',
        (document_id, asset_id),
    )
    row = cur.fetchone()
    if not row:
        return False
    stored = row[1]
    cur.execute('DELETE FROM asset_documents WHERE id = ?', (document_id,))
    delete_document_file(stored)
    return True


def delete_all_documents_for_assets(cur, asset_ids):
    if not asset_ids:
        return
    placeholders = ','.join(['?'] * len(asset_ids))
    cur.execute(
        f'SELECT stored_filename FROM asset_documents WHERE asset_id IN ({placeholders})',
        list(asset_ids),
    )
    for row in cur.fetchall():
        delete_document_file(row[0])
    cur.execute(
        f'DELETE FROM asset_documents WHERE asset_id IN ({placeholders})',
        list(asset_ids),
    )
