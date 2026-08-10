"""Clinical specialty context.

Two jobs:
  * CLINICAL_SPECIALTIES powers the "Specialty / Department" picker on the
    New Project page (CMC Vellore department list, with non-clinical and
    administrative units removed).
  * The suggestion sets make the Form Designer's instrument-name and
    field-label dropdowns adapt to the project's chosen specialty: a handful
    of specialties get tailored extras layered on top of a generic base, and
    every other specialty simply falls back to the generic base.

Everything here is plain data — offline, no dependencies. To tailor another
specialty, add an entry to SPECIALTY_EXTRAS.
"""

# --- Clinical specialties (editable box, so the list need not be exhaustive) --
CLINICAL_SPECIALTIES = [
    "Anaesthesiology",
    "Cardiac Anaesthesia",
    "Cardiology",
    "Cardiovascular and Thoracic Surgery",
    "Clinical Biochemistry",
    "Clinical Epidemiology",
    "Clinical Haematology",
    "Clinical Immunology and Rheumatology",
    "Clinical Pharmacology",
    "Community Medicine",
    "Critical Care Medicine",
    "Cytogenetics",
    "Dentistry",
    "Dermatology, Venereology and Leprosy",
    "Developmental Paediatrics",
    "Emergency Medicine",
    "Endocrine Surgery",
    "Endocrinology",
    "Family Medicine",
    "Forensic Medicine & Toxicology",
    "General Medicine",
    "General Pathology",
    "General Surgery",
    "Geriatrics",
    "Gynaecologic Oncology",
    "Hand Surgery",
    "Head and Neck Surgery",
    "Hepato Pancreato Biliary Surgery",
    "Hepatology",
    "Immuno Hematology and Blood Transfusion",
    "Infectious Diseases",
    "Interventional Radiology",
    "Medical Gastroenterology",
    "Medical Genetics",
    "Medical Oncology",
    "Microbiology",
    "Neonatology",
    "Nephrology",
    "Neuroanaesthesia",
    "Neurosciences",
    "Nuclear Medicine",
    "Obstetrics and Gynaecology",
    "Ophthalmology",
    "Orthopaedics",
    "Oto-Rhino-Laryngology",
    "Paediatric Nephrology",
    "Paediatric Neurology",
    "Paediatric Orthopaedics",
    "Paediatric Surgery",
    "Paediatrics",
    "Palliative Medicine",
    "Physical Medicine and Rehabilitation",
    "Plastic and Reconstructive Surgery",
    "Psychiatry",
    "Pulmonary Medicine",
    "Radiation Oncology",
    "Radio-diagnosis",
    "Reproductive Medicine and Surgery",
    "Respiratory Medicine",
    "Spine Surgery",
    "Trauma Surgery",
    "Urology",
    "Vascular Surgery",
    "Virology",
]

# --- Generic base — offered for every project regardless of specialty ---------
GENERIC_INSTRUMENTS = [
    "Demographics",
    "Patient History",
    "Comorbidities & Risk Factors",
    "Presenting Complaints",
    "Clinical Presentation",
    "Symptoms",
    "Physical Examination",
    "Vital Signs",
    "Laboratory Tests",
    "Microbiology",
    "Radiology / Imaging",
    "Histopathology",
    "Diagnosis",
    "Treatment – Medical",
    "Treatment – Surgical",
    "Procedures",
    "Medication History",
    "Allergies",
    "Investigations",
    "Monitoring",
    "Complications",
    "Outcomes at Discharge",
    "Follow-up",
    "Adverse Events",
    "Consent & Enrolment",
    "Family History",
    "Social History",
]

GENERIC_FIELDS = [
    "Patient Name",
    "Hospital Number",
    "Age",
    "Sex",
    "Date of Birth",
    "Date of Admission",
    "Date of Discharge",
    "Height (cm)",
    "Weight (kg)",
    "BMI",
    "Blood Pressure",
    "Heart Rate",
    "Temperature (°C)",
    "Respiratory Rate",
    "SpO₂ (%)",
    "Presenting Complaint",
    "Duration of Symptoms",
    "Diagnosis",
    "Comorbidities",
    "Diabetes Mellitus",
    "Hypertension",
    "Smoking Status",
    "Alcohol Use",
    "Hemoglobin",
    "WBC Count",
    "Platelet Count",
    "CRP",
    "ESR",
    "Creatinine",
    "Blood Glucose",
    "HbA1c",
    "Culture Result",
    "Organism Isolated",
    "Antibiotic",
    "Imaging Findings",
    "Treatment Given",
    "Complications",
    "Length of Stay (days)",
    "Outcome",
    "Follow-up Date",
    "Mortality",
    "Notes",
]

# --- Specialty-specific extras, layered ABOVE the generic base ---------------
# Add more specialties here over time; anything not listed uses the base only.
SPECIALTY_EXTRAS = {
    "Infectious Diseases": {
        "instruments": [
            "Infection Source & Site",
            "Antimicrobial Susceptibility",
            "Treatment – IV Antibiotics",
            "Treatment – Oral Antibiotics",
            "Treatment – Antifungal",
            "Antimicrobial Stewardship",
            "Sepsis / Severity Scores",
            "Source Control",
        ],
        "fields": [
            "Site of Infection",
            "Culture Specimen Type",
            "Gram Stain",
            "Colony Count",
            "Antibiotic Sensitivity",
            "MIC (µg/mL)",
            "Multidrug Resistance",
            "Procalcitonin",
            "Blood Culture Positive",
            "Fever Duration (days)",
            "Antibiotic Start Date",
            "Antibiotic Duration (days)",
            "Source Control Done",
            "HIV Status",
            "CD4 Count",
            "Immunosuppression",
        ],
    },
    "Cardiology": {
        "instruments": [
            "Cardiac Risk Factors",
            "ECG",
            "Echocardiography",
            "Coronary Angiography",
            "Cardiac Biomarkers",
            "Cath Lab / PCI",
            "Arrhythmia",
            "Heart Failure Assessment",
        ],
        "fields": [
            "Chest Pain Type",
            "NYHA Class",
            "Ejection Fraction (%)",
            "Troponin",
            "NT-proBNP",
            "ECG Rhythm",
            "QRS Duration (ms)",
            "Vessels Involved",
            "Stent Placed",
            "LDL Cholesterol",
            "Killip Class",
            "Prior Myocardial Infarction",
        ],
    },
    "Nephrology": {
        "instruments": [
            "Renal Function",
            "Urinalysis",
            "Dialysis Details",
            "Renal Biopsy",
            "Fluid & Electrolytes",
            "Transplant Details",
        ],
        "fields": [
            "Serum Creatinine",
            "eGFR",
            "Blood Urea",
            "Urine Protein",
            "Urine ACR",
            "Serum Potassium",
            "Serum Sodium",
            "CKD Stage",
            "Dialysis Modality",
            "Dialysis Vintage (months)",
            "Urine Output (mL/day)",
            "Proteinuria (g/day)",
            "Kt/V",
        ],
    },
    "Medical Oncology": {
        "instruments": [
            "Tumour Details",
            "Staging (TNM)",
            "Histopathology",
            "Chemotherapy",
            "Radiotherapy",
            "Response Assessment",
            "Toxicity (CTCAE)",
            "Survival Follow-up",
        ],
        "fields": [
            "Primary Site",
            "Histology",
            "TNM Stage",
            "Tumour Grade",
            "ECOG Performance Status",
            "Chemotherapy Regimen",
            "Cycle Number",
            "Response (RECIST)",
            "Progression-Free Survival (months)",
            "Overall Survival (months)",
            "Biomarker / Mutation",
        ],
    },
    "Neurosciences": {
        "instruments": [
            "Neurological Examination",
            "Glasgow Coma Scale",
            "Neuroimaging (CT / MRI)",
            "Stroke Assessment",
            "Seizure Details",
            "Rehabilitation",
        ],
        "fields": [
            "Glasgow Coma Scale",
            "NIHSS Score",
            "Modified Rankin Score",
            "Motor Power",
            "Cranial Nerve Involvement",
            "Seizure Type",
            "Stroke Type",
            "Time to Thrombolysis (min)",
            "MRI Findings",
        ],
    },
    "Obstetrics and Gynaecology": {
        "instruments": [
            "Obstetric History",
            "Antenatal Details",
            "Labour & Delivery",
            "Neonatal Outcome",
            "Gynaecological History",
        ],
        "fields": [
            "Gravida",
            "Parity",
            "Gestational Age (weeks)",
            "Mode of Delivery",
            "Birth Weight (g)",
            "APGAR Score",
            "Last Menstrual Period",
            "Expected Date of Delivery",
            "Booking Status",
        ],
    },
    "General Medicine": {
        "instruments": [
            "Systemic Examination",
            "Metabolic Profile",
            "Infection Screen",
        ],
        "fields": [
            "Random Blood Sugar",
            "Fasting Blood Sugar",
            "Serum Bilirubin",
            "SGOT / AST",
            "SGPT / ALT",
            "Serum Albumin",
            "TSH",
        ],
    },
}

def specialties_list():
    return CLINICAL_SPECIALTIES


def _merge(extras, generic):
    """Extras first, then the generic base, de-duplicated case-insensitively."""
    seen, out = set(), []
    for item in list(extras) + list(generic):
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def instrument_suggestions(specialty=""):
    extra = SPECIALTY_EXTRAS.get((specialty or "").strip(), {}).get("instruments", [])
    return _merge(extra, GENERIC_INSTRUMENTS)


def field_suggestions(specialty=""):
    extra = SPECIALTY_EXTRAS.get((specialty or "").strip(), {}).get("fields", [])
    return _merge(extra, GENERIC_FIELDS)
