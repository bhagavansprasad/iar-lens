import json

with open('output/delta.json') as f:
    delta = json.load(f)
with open('output/report.json') as f:
    report = json.load(f)

print('delta loaded:', delta['statistics'])
print('report loaded:', report['recommendation'])

