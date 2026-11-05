"""Evaluation documents for the professions onboarding offers: a services
contract (legal), lecture notes (students and professors) and a device manual
(engineering). Same format and rules as rag_dataset.py, which merges these in.
"""

DOCUMENTS = {
    "services_contract": [
        [
            "# Master Services Agreement",
            "This Master Services Agreement is made between Fabrikam Limited, the Customer, and "
            "Tailspin Analytics Limited, the Supplier, for the provision of a hosted analytics "
            "platform and related support services.",
            "# 1. Term and renewal",
            "This Agreement starts on 1 February 2026 and runs for an initial term of 24 months. "
            "It then renews automatically for successive 12 month periods unless either party "
            "gives at least 90 days written notice before the end of the current term.",
            "# 2. Services",
            "The Supplier will provide the analytics platform, onboarding for up to 40 named "
            "users, and support by email and telephone during business hours in the United Kingdom.",
        ],
        [
            "# 3. Fees and payment",
            "The Customer shall pay each invoice within 45 days of the invoice date. Fees are fixed "
            "for the initial term and may then increase by no more than 4 percent per year. Late "
            "payments accrue interest at 1.5 percent per month until paid in full.",
            "# 4. Service levels",
            "| Service | Availability target | Service credit",
            "| Analytics platform | 99.9 percent | 10 percent of the monthly fee",
            "| Support portal | 99.5 percent | 5 percent of the monthly fee",
            "Service credits are the sole remedy for missed availability targets and are capped at "
            "25 percent of the monthly fee in any month.",
        ],
        [
            "# 5. Data protection",
            "The Supplier shall notify the Customer of any personal data breach within 48 hours of "
            "becoming aware of it, and shall keep all Customer data within the United Kingdom.",
            "# 6. Confidentiality",
            "Each party shall keep the confidential information of the other party secret. These "
            "confidentiality obligations survive for 5 years after termination of this Agreement.",
            "# 7. Liability and termination",
            "The total liability of either party is limited to the fees paid in the 12 months "
            "before the claim. Either party may terminate this Agreement with 30 days written notice "
            "if the other party commits a material breach that is not remedied within that period.",
            "This Agreement is governed by the laws of England and Wales.",
        ],
    ],
    "thermo_lecture": [
        [
            "# Introduction to Thermodynamics, Lecture 4: Entropy",
            "The second law of thermodynamics states that the total entropy of an isolated system "
            "never decreases over time. Processes that would lower it do not happen on their own.",
            "Entropy is a measure of the number of microscopic arrangements that correspond to the "
            "macroscopic state of a system. Entropy is measured in joules per kelvin.",
            "# Reversible and irreversible processes",
            "In a reversible process the entropy of the universe stays constant. Every real process "
            "is irreversible and increases the entropy of the universe, for example heat flowing "
            "from a hot cup of tea into a cooler room.",
        ],
        [
            "# The Carnot engine",
            "The efficiency of a Carnot engine is one minus the ratio of the cold reservoir "
            "temperature to the hot reservoir temperature, with both temperatures in kelvin. No "
            "engine working between the same two reservoirs can be more efficient.",
            "An engine running between 500 kelvin and 300 kelvin has a maximum efficiency of 40 percent.",
            "| Process | Heat exchanged | Entropy change of the gas",
            "| Isothermal expansion | absorbed from the hot reservoir | positive",
            "| Adiabatic expansion | none | zero",
            "| Isothermal compression | released to the cold reservoir | negative",
        ],
        [
            "# Assessment",
            "The final exam on 14 December covers lectures 1 to 6 and counts for 60 percent of the "
            "grade. Problem sets count for 25 percent and the lab report for 15 percent.",
            "# Common mistakes",
            "Students often forget to convert temperatures from Celsius to kelvin before using the "
            "Carnot formula. Another frequent error is treating entropy as conserved, which is only "
            "true for reversible processes.",
            "# Reading",
            "Before the next lecture, read chapter 7 of the course textbook on free energy.",
        ],
    ],
    "gateway_manual": [
        [
            "# Ridgeback R7 Edge Gateway: Installation and Operation Manual",
            "# Requirements",
            "The gateway requires a 24 volt DC power supply rated for at least 2 amps. The operating "
            "temperature range is minus 20 to 60 degrees Celsius, at up to 90 percent humidity "
            "without condensation.",
            "# Network ports",
            "| Port | Protocol | Purpose",
            "| 443 | HTTPS | Management console",
            "| 1883 | MQTT | Sensor telemetry",
            "| 502 | Modbus TCP | PLC polling",
        ],
        [
            "# Installation",
            "- Mount the gateway on a 35 millimetre DIN rail inside the cabinet.",
            "- Connect the earth terminal before applying power.",
            "- Connect sensors to the RS-485 port using shielded twisted pair cable.",
            "The management console is available at 192.168.50.1 and the default username is admin. "
            "You must change the default password at first login.",
            "To restore factory settings, hold the reset button for 10 seconds until the status "
            "light turns white.",
        ],
        [
            "# Troubleshooting",
            "A flashing amber status light means the gateway cannot reach the cloud broker. Check "
            "that outbound traffic on port 1883 is allowed.",
            "A solid red status light indicates a hardware fault. Disconnect power and contact support.",
            "# Updates and logs",
            "Firmware updates are signed, and the gateway rejects any image that fails signature "
            "verification. Logs are kept for 14 days on the internal storage.",
        ],
    ],
}

QUESTIONS = [
    {"id": "ct-term", "document": "services_contract", "kind": "direct",
     "question": "How long is the initial term of the agreement?",
     "evidence": ["runs for an initial term of 24 months"], "pages": [1]},
    {"id": "ct-payment", "document": "services_contract", "kind": "direct",
     "question": "How many days does the customer have to pay an invoice?",
     "evidence": ["pay each invoice within 45 days of the invoice date"], "pages": [2]},
    {"id": "ct-breach-notice", "document": "services_contract", "kind": "direct",
     "question": "How quickly must a personal data breach be reported?",
     "evidence": ["personal data breach within 48 hours"], "pages": [3]},
    {"id": "ct-renewal-notice", "document": "services_contract", "kind": "distractor",
     "question": "How much notice is needed to stop the contract renewing?",
     "evidence": ["gives at least 90 days written notice"], "pages": [1]},
    {"id": "ct-termination-breach", "document": "services_contract", "kind": "distractor",
     "question": "Can we end the contract early if the supplier breaks it, and with what notice?",
     "evidence": ["terminate this Agreement with 30 days written notice"], "pages": [3]},
    {"id": "ct-platform-credit", "document": "services_contract", "kind": "table",
     "question": "What service credit applies if the analytics platform misses its target?",
     "evidence": ["Analytics platform | 99.9 percent | 10 percent of the monthly fee"], "pages": [2]},
    {"id": "ct-confidentiality", "document": "services_contract", "kind": "direct",
     "question": "How long do the confidentiality duties last after the contract ends?",
     "evidence": ["survive for 5 years after termination"], "pages": [3]},
    {"id": "ct-liability", "document": "services_contract", "kind": "direct",
     "question": "What is the cap on liability?",
     "evidence": ["limited to the fees paid in the 12 months before the claim"], "pages": [3]},
    {"id": "ct-fees-late", "document": "services_contract", "kind": "multi",
     "question": "Can fees go up after the initial term, and what happens if we pay late?",
     "evidence": ["increase by no more than 4 percent per year", "interest at 1.5 percent per month"],
     "pages": [2]},
    {"id": "ct-insurance", "document": "services_contract", "kind": "no_answer",
     "question": "How much professional indemnity insurance must the supplier hold?",
     "evidence": [], "pages": []},

    {"id": "lc-second-law", "document": "thermo_lecture", "kind": "direct",
     "question": "What does the second law of thermodynamics say?",
     "evidence": ["total entropy of an isolated system never decreases over time"], "pages": [1]},
    {"id": "lc-units", "document": "thermo_lecture", "kind": "direct",
     "question": "What are the units of entropy?",
     "evidence": ["Entropy is measured in joules per kelvin"], "pages": [1]},
    {"id": "lc-carnot-formula", "document": "thermo_lecture", "kind": "direct",
     "question": "How do you calculate the efficiency of a Carnot engine?",
     "evidence": ["one minus the ratio of the cold reservoir temperature to the hot reservoir temperature"],
     "pages": [2]},
    {"id": "lc-example", "document": "thermo_lecture", "kind": "distractor",
     "question": "What is the maximum efficiency of an engine between 500 K and 300 K?",
     "evidence": ["has a maximum efficiency of 40 percent"], "pages": [2]},
    {"id": "lc-exam-weight", "document": "thermo_lecture", "kind": "distractor",
     "question": "How much is the final exam worth?",
     "evidence": ["counts for 60 percent of the grade"], "pages": [3]},
    {"id": "lc-adiabatic", "document": "thermo_lecture", "kind": "table",
     "question": "What is the entropy change of the gas during adiabatic expansion?",
     "evidence": ["Adiabatic expansion | none | zero"], "pages": [2]},
    {"id": "lc-mistake", "document": "thermo_lecture", "kind": "direct",
     "question": "What mistake do students often make with the Carnot formula?",
     "evidence": ["forget to convert temperatures from Celsius to kelvin"], "pages": [3]},
    {"id": "lc-reversible", "document": "thermo_lecture", "kind": "direct",
     "question": "What happens to the entropy of the universe in a reversible process?",
     "evidence": ["In a reversible process the entropy of the universe stays constant"], "pages": [1]},
    {"id": "lc-grading", "document": "thermo_lecture", "kind": "multi",
     "question": "How is the course graded between the exam, problem sets and the lab report?",
     "evidence": ["counts for 60 percent of the grade", "Problem sets count for 25 percent"],
     "pages": [3]},
    {"id": "lc-office-hours", "document": "thermo_lecture", "kind": "no_answer",
     "question": "When are the office hours for this course?", "evidence": [], "pages": []},

    {"id": "mn-power", "document": "gateway_manual", "kind": "direct",
     "question": "What power supply does the gateway need?",
     "evidence": ["requires a 24 volt DC power supply rated for at least 2 amps"], "pages": [1]},
    {"id": "mn-mqtt-port", "document": "gateway_manual", "kind": "table",
     "question": "Which port is used for sensor telemetry?",
     "evidence": ["1883 | MQTT | Sensor telemetry"], "pages": [1]},
    {"id": "mn-console", "document": "gateway_manual", "kind": "direct",
     "question": "What is the address of the management console?",
     "evidence": ["management console is available at 192.168.50.1"], "pages": [2]},
    {"id": "mn-reset", "document": "gateway_manual", "kind": "distractor",
     "question": "How do I restore factory settings?",
     "evidence": ["hold the reset button for 10 seconds"], "pages": [2]},
    {"id": "mn-logs", "document": "gateway_manual", "kind": "distractor",
     "question": "How long are logs stored?",
     "evidence": ["Logs are kept for 14 days on the internal storage"], "pages": [3]},
    {"id": "mn-amber", "document": "gateway_manual", "kind": "direct",
     "question": "What does a flashing amber light mean?",
     "evidence": ["flashing amber status light means the gateway cannot reach the cloud broker"],
     "pages": [3]},
    {"id": "mn-temperature", "document": "gateway_manual", "kind": "direct",
     "question": "Can the gateway run in a freezing warehouse?",
     "evidence": ["operating temperature range is minus 20 to 60 degrees Celsius"], "pages": [1]},
    {"id": "mn-firmware", "document": "gateway_manual", "kind": "direct",
     "question": "What happens if a firmware image is not properly signed?",
     "evidence": ["rejects any image that fails signature verification"], "pages": [3]},
    {"id": "mn-first-steps", "document": "gateway_manual", "kind": "multi",
     "question": "What should I connect before powering on, and what must I change at first login?",
     "evidence": ["Connect the earth terminal before applying power", "change the default password at first login"],
     "pages": [2]},
    {"id": "mn-warranty", "document": "gateway_manual", "kind": "no_answer",
     "question": "How long is the warranty on the gateway?", "evidence": [], "pages": []},
]
