SafeTell package for {{ e.name }}
Prepared with SafeTell Onboard.

Files:
{% for f in files %}  - {{ f }}
{% endfor %}
Order in SafeTell:
  1. Onboarding page: upload the workbook, fix anything the check reports, import.
  2. Ask the team to accept their invitations (permits need their GC signers to be members).
  3. Onboarding page > Import history: upload each history_<section>.xlsx in its section (check first, then import).
  4. Inspection templates > Import Excel: the checklist file(s).
  5. requirements.json: {{ p.requirements|length }} reviewed requirements with citations.
{% for w in p.warnings %}
Warning: {{ w }}{% endfor %}
