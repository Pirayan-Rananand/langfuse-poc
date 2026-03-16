```
Flow:
  START
    ↓
  emotional_gate  (runs every turn)
    ├─ distressed → comfort → END
    └─ ok →
         [assessment not completed] → assessment
           ├─ still_gathering → END  (returns next question)
           └─ data_complete → classifier
                ├─ RED    → escalate → END
                ├─ YELLOW → coach → END
                ├─ ORANGE → coach → END
                └─ HEALTHY→ coach → END
         [assessment completed] →
           ├─ debt_case == "red" → escalate → END
           └─ else → coach → END
```
