import re

with open('pruebas/debug_fb.html', 'r', encoding='utf-8') as f:
    c = f.read()

links = re.findall(r'aria-label="([^"]+?), listing (\d+)"', c)
print(f'Total: {len(links)}')
for n, i in links:
    print(f'  - {n} (listing {i})')
