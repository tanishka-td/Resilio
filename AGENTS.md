# Resilio project guidance

- The project owner is working alone and values a simple, understandable implementation.
- Work phase by phase. Phases 1 and 2 are complete. Phases 3 and 4 cover the backend inventory simulator and scenario response comparison. Do not create or edit website, frontend, or UI files until the owner explicitly approves that phase.
- The Kaggle supply-chain inventory dataset is only a candidate until its actual contents are audited. Its listing describes it as synthetic. Do not describe its results as real-world evidence.
- Never invent missing stock, demand, lead-time, supplier, or disruption values. Identify missing inputs and discuss whether to change datasets or clearly label assumptions.
- Keep downloaded raw data out of version control. Do not copy it into generated reports.
- Keep explanations, assumptions, and calculations understandable to a beginner.
- For forecasting later, use chronological evaluation and compare against a simple baseline. Check feature availability to avoid leakage.
- Disruptions are user-selected scenarios unless a trustworthy real-time signal source is added. Do not claim the system predicts disasters.
- The website will use HTML, CSS, and JavaScript. Python remains the data and machine-learning environment unless the owner changes this decision.
- The simulator must require user-provided starting stock and planned order quantity. Do not use the CSV's historical inventory or order quantities as trustworthy forward simulation inputs.
- Do not claim to compare financial costs until holding costs and shortage penalties are supplied or clearly labeled as user assumptions.
