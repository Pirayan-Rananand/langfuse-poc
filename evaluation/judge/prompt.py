"""Build the judge prompt for a single evaluation item."""

from evaluation.dataset.schema import DatasetItemExpectedOutput, DatasetItemInput
from evaluation.judge.dimensions import DIMENSIONS


def build_judge_prompt(
    item_input: DatasetItemInput,
    candidate_output: str,
    expected_output: DatasetItemExpectedOutput,
) -> str:
    conversation_text = "\n".join(
        f"[{m['role'].upper()}]: {m['content']}" for m in item_input["messages"]
    )

    dimensions_rubric = "\n\n".join(
        f"### {d.name} (น้ำหนัก {d.weight:.0%})\n{d.rubric}" for d in DIMENSIONS
    )

    return f"""คุณเป็น AI Judge ที่ประเมินคุณภาพของ AI Money Coach ที่ตอบเป็นภาษาไทย

## บทสนทนา
{conversation_text}

## บริบทการเงิน
- ประเภทหนี้: {item_input.get('debt_case', 'unknown')}
- สถานะการประเมิน: {item_input.get('assessment_phase', 'completed')}

## คำตอบอ้างอิง (Gold Reference)
{expected_output['final_message']}

## คำตอบที่ต้องประเมิน (Candidate)
{candidate_output}

## เกณฑ์การประเมิน
{dimensions_rubric}

## คำสั่ง
ประเมินคำตอบ Candidate ในแต่ละมิติด้วยคะแนน 0-10 โดยเทียบกับ Gold Reference และบริบทของบทสนทนา
ตอบด้วย JSON เท่านั้น ในรูปแบบต่อไปนี้ (ไม่มีข้อความอื่น):
{{
  "financial_accuracy": {{"score": <0-10>, "reasoning": "<อธิบายสั้นๆ>"}},
  "advice_actionability": {{"score": <0-10>, "reasoning": "<อธิบายสั้นๆ>"}},
  "completeness": {{"score": <0-10>, "reasoning": "<อธิบายสั้นๆ>"}},
  "empathy": {{"score": <0-10>, "reasoning": "<อธิบายสั้นๆ>"}},
  "language_quality": {{"score": <0-10>, "reasoning": "<อธิบายสั้นๆ>"}}
}}"""
