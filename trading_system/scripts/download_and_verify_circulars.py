import os
import urllib.request
import hashlib
from pypdf import PdfReader
from io import BytesIO

os.makedirs('trading_system/data/circulars', exist_ok=True)

urls = [
    ('2024-09-25', 'https://www.niftyindices.com/Press_Release/ind_prs25092024.pdf', 'ind_prs25092024.pdf'),
    ('2024-02-28', 'https://www.niftyindices.com/Press_Release/ind_prs28022024.pdf', 'ind_prs28022024.pdf'),
    ('2024-04-24', 'https://www.niftyindices.com/Press_Release/ind_prs24042024.pdf', 'ind_prs24042024.pdf'),
    ('2024-12-02', 'https://www.niftyindices.com/Press_Release/ind_prs02122024.pdf', 'ind_prs02122024.pdf'),
    ('2021-10-22', 'https://www.niftyindices.com/Press_Release/ind_prs22102021.pdf', 'ind_prs22102021.pdf'),
    ('2025-01-24', 'https://www.niftyindices.com/Press_Release/ind_prs24012025.pdf', 'ind_prs24012025.pdf'),
    ('2019-08-28', 'https://www.niftyindices.com/Press_Release/ind_prs28082019.pdf', 'ind_prs28082019.pdf'),
    ('2019-02-18', 'https://www.niftyindices.com/Press_Release/ind_prs18022019.pdf', 'ind_prs18022019.pdf'),
    ('2018-08-28', 'https://www.niftyindices.com/Press_Release/ind_prs28082018.pdf', 'ind_prs28082018.pdf'),
    ('2016-02-22', 'https://www.niftyindices.com/Press_Release/ind_prs22022016.pdf', 'ind_prs22022016.pdf'),
    ('2015-08-12', 'https://www.niftyindices.com/Press_Release/ind_prs12082015.pdf', 'ind_prs12082015.pdf')
]

for dt, u, fn in urls:
    dest = os.path.join('trading_system/data/circulars', fn)
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
            with open(dest, 'wb') as f:
                f.write(data)
            sha = hashlib.sha256(data).hexdigest()
            reader = PdfReader(BytesIO(data))
            text = '\n'.join([p.extract_text() or '' for p in reader.pages[:3]])
            has_nifty50 = 'nifty 50' in text.lower() or 'cnx nifty' in text.lower() or 's&p cnx nifty' in text.lower()
            first_line = text.split('\n')[0] if text else ''
            print(f"SAVED: {fn} | Size: {len(data)} | SHA256: {sha[:16]}... | Nifty50: {has_nifty50} | FirstLine: {first_line[:60]}")
    except Exception as e:
        print(f"FAILED: {fn} -> {e}")
