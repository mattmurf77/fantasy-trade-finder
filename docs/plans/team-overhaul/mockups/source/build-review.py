from pathlib import Path

root = Path(__file__).resolve().parent
shell = (root / 'review-shell.html').read_text()
modules = ['questions.js', 'setup-mocks.js', 'execution-mocks.js', 'review-app.js']
scripts = '\n'.join('<script>\n' + (root / name).read_text() + '\n</script>' for name in modules)
assert shell.count('<!-- MODULES -->') == 1
output = root.parent / 'team-overhaul-review.html'
output.write_text(shell.replace('<!-- MODULES -->', scripts))
print(f'{output}: {output.stat().st_size:,} bytes')
