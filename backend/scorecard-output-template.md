# Scorecard output template

[The JSON template](scorecard-output-template.json) proposes a consistent output
structure for the active rubric. Every value is a placeholder, with no sample
report data, evidence, judgments, or scores. Criterion IDs are fixed keys taken
from `backend/Rubrics/active_rubric.txt`.

When filling in the template:

- Keep all section and criterion keys. Evaluate each criterion once.
- Replace every `"Your Answer"` placeholder; never return placeholder text in a
  completed evaluation.
- Include only scores in the JSON output: criterion scores, section totals, and
  the overall total.
- Replace score placeholders with JSON numbers, without quotation marks. Use
  only the point values permitted for that specific criterion by the rubric.
- Calculate each `section_score` from its criterion scores and calculate
  `total_calculated_score` from the section scores.
- Return only the JSON object, without Markdown fences or surrounding prose.

This is a proposed output template, not a validation schema. Its score values
are strings solely to keep the blank template free of example data. The current
`Scorecard` model in `backend/watcher.py` stores one evaluation per section;
adopting this criterion-level structure requires updating that model and any
consumers. For consistent production output, enforce the structure and allowed
scores with a validation schema, validate returned results, and calculate totals
in application code.
