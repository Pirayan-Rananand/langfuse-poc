"""Five evaluation dimensions for Thai-language financial coaching responses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    name: str
    weight: float
    description: str
    rubric: str


DIMENSIONS: list[Dimension] = [
    Dimension(
        name="financial_accuracy",
        weight=0.30,
        description="ความถูกต้องของข้อมูลทางการเงิน",
        rubric=(
            "ตัวเลขถูกต้อง (รายได้ รายจ่าย หนี้) กลยุทธ์การชำระหนี้เหมาะสมกับกรณี "
            "(avalanche vs snowball) อัตราส่วน DTI คำนวณถูกต้อง ไม่มีข้อมูลทางการเงินที่ผิดพลาด"
        ),
    ),
    Dimension(
        name="advice_actionability",
        weight=0.25,
        description="ความเป็นรูปธรรมของคำแนะนำ",
        rubric=(
            "มีขั้นตอนที่ทำได้จริงและชัดเจน ระบุจำนวนเงินและระยะเวลาที่แน่นอน "
            "ไม่ใช่คำแนะนำที่คลุมเครือหรือทั่วไปเกินไป"
        ),
    ),
    Dimension(
        name="completeness",
        weight=0.20,
        description="ความครบถ้วนของการตอบ",
        rubric=(
            "ตอบครอบคลุมความกังวลของผู้ใช้ทั้งหมด ไม่ข้ามประเด็นสำคัญ "
            "หากมีหลายปัญหาต้องระบุแผนสำหรับแต่ละปัญหา"
        ),
    ),
    Dimension(
        name="empathy",
        weight=0.15,
        description="ความอ่อนโยนและการไม่ตัดสิน",
        rubric=(
            "โทนเสียงอบอุ่น ไม่วิจารณ์หรือตัดสิน รับรู้ความกังวลของผู้ใช้ "
            "สร้างแรงบันดาลใจโดยไม่สร้างความรู้สึกผิด"
        ),
    ),
    Dimension(
        name="language_quality",
        weight=0.10,
        description="คุณภาพภาษาไทย",
        rubric=(
            "ภาษาไทยเป็นธรรมชาติ ใช้ระดับภาษาที่เหมาะสม (สุภาพแต่ไม่เป็นทางการเกินไป) "
            "ไม่มีคำทับศัพท์ที่ไม่จำเป็น"
        ),
    ),
]

assert abs(sum(d.weight for d in DIMENSIONS) - 1.0) < 1e-9, "Weights must sum to 1.0"
