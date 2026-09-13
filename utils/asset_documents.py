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

DOC_CATEGORY_SUPPORTING = 'supporting'
DOC_CATEGORY_RETURN = 'return'
DOC_CATEGORY_PREVIOUS_OWNER = 'previous_owner'
DOC_CATEGORIES = (
    DOC_CATEGORY_SUPPORTING,
    DOC_CATEGORY_RETURN,
    DOC_CATEGORY_PREVIOUS_OWNER,
)


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


def _normalize_doc_category(value):
    if value in (DOC_CATEGORY_RETURN, DOC_CATEGORY_PREVIOUS_OWNER):
        return value
    return DOC_CATEGORY_SUPPORTING


def nonempty_uploaded_files(file_storages):
    return [
        f for f in (file_storages or [])
        if f and getattr(f, 'filename', None) and str(f.filename).strip()
    ]


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
            doc_category TEXT NOT NULL DEFAULT 'supporting',
            FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE
        )
    ''')
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_asset_documents_asset_id '
        'ON asset_documents(asset_id)'
    )
    cur.execute('PRAGMA table_info(asset_documents)')
    columns = [row[1] for row in cur.fetchall()]
    if 'doc_category' not in columns:
        cur.execute(
            'ALTER TABLE asset_documents ADD COLUMN doc_category TEXT DEFAULT "supporting"'
        )
        cur.execute(
            '''
            UPDATE asset_documents
            SET doc_category = ?
            WHERE doc_category IS NULL OR TRIM(doc_category) = ''
            ''',
            (DOC_CATEGORY_SUPPORTING,),
        )


def _document_dict(row):
    asset_id = row[1]
    category = DOC_CATEGORY_SUPPORTING
    if len(row) > 7:
        category = _normalize_doc_category(row[7])
    return {
        'id': row[0],
        'asset_id': asset_id,
        'original_filename': row[2],
        'stored_filename': row[3],
        'content_type': row[4],
        'file_size': row[5] or 0,
        'created_at': row[6],
        'doc_category': category,
        'download_url': f'/assets/{asset_id}/documents/{row[0]}/download',
    }


def list_documents_for_asset(cur, asset_id):
    cur.execute(
        '''
        SELECT id, asset_id, original_filename, stored_filename, content_type, file_size, created_at, doc_category
        FROM asset_documents
        WHERE asset_id = ?
        ORDER BY created_at, id
        ''',
        (asset_id,),
    )
    return [_document_dict(row) for row in cur.fetchall()]


def list_documents_grouped_by_asset_ids(cur, asset_ids):
    """Return {asset_id: [doc_dict, ...]} for the given asset ids."""
    grouped = {int(aid): [] for aid in asset_ids or []}
    if not asset_ids:
        return grouped
    placeholders = ','.join(['?'] * len(asset_ids))
    cur.execute(
        f'''
        SELECT id, asset_id, original_filename, stored_filename, content_type, file_size, created_at, doc_category
        FROM asset_documents
        WHERE asset_id IN ({placeholders})
        ORDER BY asset_id, created_at, id
        ''',
        list(asset_ids),
    )
    for row in cur.fetchall():
        aid = row[1]
        grouped.setdefault(aid, []).append(_document_dict(row))
    return grouped


def save_uploaded_file_for_asset(cur, asset_id, file_storage, doc_category=DOC_CATEGORY_SUPPORTING):
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

    category = _normalize_doc_category(doc_category)
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
            (asset_id, original_filename, stored_filename, content_type, file_size, doc_category)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (asset_id, original, stored, content_type, size, category),
    )
    doc_id = cur.lastrowid
    return {
        'id': doc_id,
        'asset_id': asset_id,
        'original_filename': original,
        'stored_filename': stored,
        'content_type': content_type,
        'file_size': size,
        'doc_category': category,
        'download_url': f'/assets/{asset_id}/documents/{doc_id}/download',
    }, None


def save_uploaded_files_for_assets(cur, asset_ids, file_storages, doc_category=DOC_CATEGORY_SUPPORTING):
    """
    Save each upload once, then copy the stored file to every other asset id.
    Returns (saved_count, error_message).
    """
    asset_ids = [int(a) for a in asset_ids if a is not None]
    if not asset_ids:
        return 0, None
    files = nonempty_uploaded_files(file_storages)
    if not files:
        return 0, None
    if len(files) > MAX_DOCUMENTS_PER_UPLOAD:
        return 0, f'You can upload at most {MAX_DOCUMENTS_PER_UPLOAD} files at once.'

    category = _normalize_doc_category(doc_category)
    saved = 0
    first_id = asset_ids[0]
    for file_storage in files:
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        first_doc, err = save_uploaded_file_for_asset(
            cur, first_id, file_storage, doc_category=category
        )
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
                    (asset_id, original_filename, stored_filename, content_type, file_size, doc_category)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    other_id,
                    first_doc['original_filename'],
                    stored,
                    first_doc['content_type'],
                    first_doc['file_size'],
                    category,
                ),
            )
            saved += 1
    return saved, None


def reclassify_supporting_documents_as_previous_owner(cur, asset_ids):
    """Move current supporting docs to previous-owner so a new owner can attach fresh files."""
    ids = [int(a) for a in (asset_ids or []) if a is not None]
    if not ids:
        return
    placeholders = ','.join(['?'] * len(ids))
    cur.execute(
        f'''
        UPDATE asset_documents
        SET doc_category = ?
        WHERE asset_id IN ({placeholders}) AND doc_category = ?
        ''',
        [DOC_CATEGORY_PREVIOUS_OWNER] + ids + [DOC_CATEGORY_SUPPORTING],
    )


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
