import sqlite3, json
conn = sqlite3.connect('autotrader.db')
conn.row_factory = sqlite3.Row
docs = [dict(r) for r in conn.execute('SELECT title, doc_type, version, slug, is_active, show_in_footer, show_in_nav, show_in_signup, footer_order, content, content_hash FROM legal_documents').fetchall()]
with open('docs_export.json', 'w') as f:
    json.dump(docs, f)
print('Exported', len(docs), 'docs to docs_export.json')
conn.close()
