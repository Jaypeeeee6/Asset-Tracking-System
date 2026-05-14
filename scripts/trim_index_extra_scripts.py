# -*- coding: utf-8 -*-
path = r"C:\Users\glori\Asset-Tracking-System - Copy\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()
marker = "{% block extra_scripts %}"
if marker not in text:
    raise SystemExit("extra_scripts block missing")
pre, rest = text.split(marker, 1)
subpost = rest.split("{% endblock %}", 1)
if len(subpost) != 2:
    raise SystemExit("unexpected split")
post = subpost[1]
new_body = (
    "\n<script src=\"https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js\"></script>\n"
    "{% include 'partials/dashboard_main_script.html' %}\n"
)
new_text = pre + marker + new_body + "{% endblock %}" + post
with open(path, "w", encoding="utf-8") as f:
    f.write(new_text)
print("extra_scripts replaced, len", len(text), "->", len(new_text))
