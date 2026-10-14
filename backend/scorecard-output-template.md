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

The watcher and API use this JSON template as their structured-output schema.
The `"Your Answer"` placeholders are interpreted as numeric values, and the
template's keys define the required output structure. Update this template when
the active rubric's section or criterion IDs change.
