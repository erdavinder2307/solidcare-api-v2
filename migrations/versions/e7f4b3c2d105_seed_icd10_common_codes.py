"""seed_icd10_common_codes

Revision ID: e7f4b3c2d105
Revises: d5f3a2b1c904
Create Date: 2026-06-12

Seeds ~150 common ICD-10-CM codes into the icd10_codes reference table.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "e7f4b3c2d105"
down_revision = "d5f3a2b1c904"
branch_labels = None
depends_on = None

# fmt: off
ICD10_SEED = [
    # Chapter I — Certain infectious and parasitic diseases
    ("A00", "Cholera", "Intestinal infectious diseases", "Chapter I", True),
    ("A09", "Other gastroenteritis and colitis", "Intestinal infectious diseases", "Chapter I", True),
    ("A15.0", "Tuberculosis of lung", "Tuberculosis", "Chapter I", True),
    ("A41.9", "Sepsis, unspecified organism", "Other bacterial diseases", "Chapter I", True),
    ("A90", "Dengue fever", "Arthropod-borne viral fevers", "Chapter I", True),
    ("B34.9", "Viral infection, unspecified", "Other viral diseases", "Chapter I", True),
    # Chapter II — Neoplasms
    ("C34.10", "Malignant neoplasm of upper lobe of bronchus or lung, unspecified", "Malignant neoplasms", "Chapter II", True),
    ("C50.911", "Malignant neoplasm of unspecified site of right female breast", "Malignant neoplasms", "Chapter II", True),
    ("C18.9", "Malignant neoplasm of colon, unspecified", "Malignant neoplasms", "Chapter II", True),
    ("D64.9", "Anaemia, unspecified", "Other nutritional anaemias", "Chapter II", True),
    # Chapter III — Diseases of the blood
    ("D50.9", "Iron deficiency anaemia, unspecified", "Iron deficiency anaemia", "Chapter III", True),
    ("D69.6", "Thrombocytopenia, unspecified", "Purpura and other haemorrhagic conditions", "Chapter III", True),
    # Chapter IV — Endocrine, nutritional and metabolic diseases
    ("E10.9", "Type 1 diabetes mellitus without complications", "Diabetes mellitus", "Chapter IV", True),
    ("E11.9", "Type 2 diabetes mellitus without complications", "Diabetes mellitus", "Chapter IV", True),
    ("E11.65", "Type 2 diabetes mellitus with hyperglycaemia", "Diabetes mellitus", "Chapter IV", True),
    ("E13.9", "Other specified diabetes mellitus without complications", "Diabetes mellitus", "Chapter IV", True),
    ("E03.9", "Hypothyroidism, unspecified", "Thyroid disorders", "Chapter IV", True),
    ("E05.90", "Thyrotoxicosis, unspecified, without thyrotoxic crisis", "Thyroid disorders", "Chapter IV", True),
    ("E78.5", "Hyperlipidaemia, unspecified", "Metabolic disorders", "Chapter IV", True),
    ("E66.9", "Obesity, unspecified", "Obesity and other hyperalimentation", "Chapter IV", True),
    ("E11.40", "Type 2 diabetes mellitus with diabetic neuropathy, unspecified", "Diabetes mellitus", "Chapter IV", True),
    ("E11.36", "Type 2 diabetes mellitus with diabetic cataract", "Diabetes mellitus", "Chapter IV", True),
    # Chapter V — Mental and behavioural disorders
    ("F32.9", "Major depressive disorder, single episode, unspecified", "Mood disorders", "Chapter V", True),
    ("F41.1", "Generalized anxiety disorder", "Neurotic disorders", "Chapter V", True),
    ("F10.10", "Alcohol abuse, uncomplicated", "Mental disorders due to psychoactive substances", "Chapter V", True),
    ("F20.9", "Schizophrenia, unspecified", "Schizophrenia, schizotypal and delusional disorders", "Chapter V", True),
    # Chapter VI — Diseases of the nervous system
    ("G43.909", "Migraine, unspecified, not intractable, without status migrainosus", "Migraine", "Chapter VI", True),
    ("G40.909", "Epilepsy, unspecified, not intractable, without status epilepticus", "Epilepsy", "Chapter VI", True),
    ("G35", "Multiple sclerosis", "Demyelinating diseases", "Chapter VI", True),
    ("G47.00", "Insomnia, unspecified", "Sleep disorders", "Chapter VI", True),
    # Chapter VII — Diseases of the eye
    ("H25.9", "Age-related cataract, unspecified", "Disorders of lens", "Chapter VII", True),
    ("H35.30", "Unspecified macular degeneration", "Retinal disorders", "Chapter VII", True),
    ("H40.10X0", "Open-angle glaucoma, unspecified, stage unspecified", "Glaucoma", "Chapter VII", True),
    # Chapter VIII — Diseases of the ear
    ("H81.10", "Benign paroxysmal vertigo, unspecified ear", "Diseases of inner ear", "Chapter VIII", True),
    ("H91.90", "Unspecified hearing loss, unspecified ear", "Other hearing disorders", "Chapter VIII", True),
    # Chapter IX — Diseases of the circulatory system
    ("I10", "Essential (primary) hypertension", "Hypertensive diseases", "Chapter IX", True),
    ("I11.9", "Hypertensive heart disease without heart failure", "Hypertensive diseases", "Chapter IX", True),
    ("I20.9", "Angina pectoris, unspecified", "Ischaemic heart diseases", "Chapter IX", True),
    ("I21.9", "Acute myocardial infarction, unspecified", "Ischaemic heart diseases", "Chapter IX", True),
    ("I25.10", "Atherosclerotic heart disease of native coronary artery without angina pectoris", "Ischaemic heart diseases", "Chapter IX", True),
    ("I48.91", "Unspecified atrial fibrillation", "Other cardiac arrhythmias", "Chapter IX", True),
    ("I50.9", "Heart failure, unspecified", "Heart failure", "Chapter IX", True),
    ("I63.9", "Cerebral infarction, unspecified", "Cerebrovascular diseases", "Chapter IX", True),
    ("I64", "Stroke, not specified as haemorrhage or infarction", "Cerebrovascular diseases", "Chapter IX", True),
    ("I83.90", "Varicose veins of unspecified lower extremity without ulcer or inflammation", "Diseases of veins", "Chapter IX", True),
    # Chapter X — Diseases of the respiratory system
    ("J00", "Acute nasopharyngitis (common cold)", "Acute upper respiratory infections", "Chapter X", True),
    ("J01.90", "Acute sinusitis, unspecified", "Acute upper respiratory infections", "Chapter X", True),
    ("J02.9", "Acute pharyngitis, unspecified", "Acute upper respiratory infections", "Chapter X", True),
    ("J03.90", "Acute tonsillitis, unspecified", "Acute upper respiratory infections", "Chapter X", True),
    ("J06.9", "Acute upper respiratory infection, unspecified", "Acute upper respiratory infections", "Chapter X", True),
    ("J18.9", "Pneumonia, unspecified organism", "Influenza and pneumonia", "Chapter X", True),
    ("J20.9", "Acute bronchitis, unspecified", "Other acute lower respiratory infections", "Chapter X", True),
    ("J30.9", "Allergic rhinitis, unspecified", "Other diseases of upper respiratory tract", "Chapter X", True),
    ("J45.20", "Mild intermittent asthma, uncomplicated", "Chronic lower respiratory diseases", "Chapter X", True),
    ("J45.41", "Moderate persistent asthma with (acute) exacerbation", "Chronic lower respiratory diseases", "Chapter X", True),
    ("J44.1", "Chronic obstructive pulmonary disease with (acute) exacerbation", "Chronic lower respiratory diseases", "Chapter X", True),
    # Chapter XI — Diseases of the digestive system
    ("K21.0", "Gastro-oesophageal reflux disease with oesophagitis", "Diseases of oesophagus", "Chapter XI", True),
    ("K25.9", "Gastric ulcer, unspecified", "Peptic ulcer disease", "Chapter XI", True),
    ("K29.70", "Gastritis, unspecified, without bleeding", "Gastritis and duodenitis", "Chapter XI", True),
    ("K30", "Functional dyspepsia", "Other diseases of stomach and duodenum", "Chapter XI", True),
    ("K37", "Unspecified appendicitis", "Diseases of appendix", "Chapter XI", True),
    ("K57.90", "Diverticulosis of intestine, unspecified, without perforation, abscess, or bleeding", "Diverticular disease", "Chapter XI", True),
    ("K59.00", "Constipation, unspecified", "Other functional intestinal disorders", "Chapter XI", True),
    ("K74.60", "Unspecified cirrhosis of liver", "Fibrosis and cirrhosis of liver", "Chapter XI", True),
    ("K76.0", "Fatty (change of) liver, not elsewhere classified", "Other diseases of liver", "Chapter XI", True),
    ("K80.20", "Calculus of gallbladder without cholecystitis, without obstruction", "Cholelithiasis", "Chapter XI", True),
    ("K92.1", "Melaena", "Other diseases of digestive system", "Chapter XI", True),
    # Chapter XII — Diseases of the skin
    ("L20.9", "Atopic dermatitis, unspecified", "Dermatitis and eczema", "Chapter XII", True),
    ("L40.0", "Psoriasis vulgaris", "Papulosquamous disorders", "Chapter XII", True),
    ("L50.0", "Allergic urticaria", "Urticaria and erythema", "Chapter XII", True),
    ("L70.0", "Acne vulgaris", "Acne", "Chapter XII", True),
    # Chapter XIII — Diseases of the musculoskeletal system
    ("M10.9", "Gout, unspecified", "Crystal arthropathies", "Chapter XIII", True),
    ("M06.9", "Rheumatoid arthritis, unspecified", "Inflammatory polyarthropathies", "Chapter XIII", True),
    ("M15.9", "Polyosteoarthritis, unspecified", "Arthrosis", "Chapter XIII", True),
    ("M17.9", "Osteoarthritis of knee, unspecified", "Arthrosis", "Chapter XIII", True),
    ("M19.90", "Unspecified osteoarthritis, unspecified site", "Arthrosis", "Chapter XIII", True),
    ("M47.816", "Spondylosis without myelopathy or radiculopathy, lumbar region", "Spondylopathies", "Chapter XIII", True),
    ("M54.5", "Low back pain", "Dorsopathies", "Chapter XIII", True),
    ("M79.3", "Panniculitis, unspecified", "Other soft tissue disorders", "Chapter XIII", True),
    ("M81.0", "Age-related osteoporosis without current pathological fracture", "Osteoporosis", "Chapter XIII", True),
    # Chapter XIV — Diseases of the genitourinary system
    ("N18.3", "Chronic kidney disease, stage 3", "Chronic kidney disease", "Chapter XIV", True),
    ("N18.9", "Chronic kidney disease, unspecified", "Chronic kidney disease", "Chapter XIV", True),
    ("N20.0", "Calculus of kidney", "Urolithiasis", "Chapter XIV", True),
    ("N39.0", "Urinary tract infection, site not specified", "Other diseases of urinary system", "Chapter XIV", True),
    ("N40.1", "Benign prostatic hyperplasia with lower urinary tract symptoms", "Diseases of male genital organs", "Chapter XIV", True),
    # Chapter XV — Pregnancy, childbirth and the puerperium
    ("O10.919", "Unspecified pre-existing hypertension complicating pregnancy, unspecified trimester", "Oedema, proteinuria and hypertensive disorders", "Chapter XV", True),
    ("O80", "Encounter for full-term uncomplicated delivery", "Delivery", "Chapter XV", True),
    # Chapter XVI — Certain conditions originating in the perinatal period
    ("P07.39", "Other preterm newborn, unspecified weeks of gestation", "Disorders related to short gestation", "Chapter XVI", True),
    # Chapter XVII — Congenital malformations
    ("Q21.1", "Atrial septal defect", "Congenital malformations of cardiac septa", "Chapter XVII", True),
    # Chapter XVIII — Symptoms, signs and abnormal clinical findings
    ("R00.0", "Tachycardia, unspecified", "Symptoms and signs involving the circulatory and respiratory systems", "Chapter XVIII", True),
    ("R05", "Cough", "Symptoms and signs involving the circulatory and respiratory systems", "Chapter XVIII", True),
    ("R06.0", "Dyspnoea", "Symptoms and signs involving the circulatory and respiratory systems", "Chapter XVIII", True),
    ("R10.9", "Unspecified abdominal pain", "Symptoms and signs involving the digestive system", "Chapter XVIII", True),
    ("R11.0", "Nausea", "Symptoms and signs involving the digestive system", "Chapter XVIII", True),
    ("R11.10", "Vomiting, unspecified", "Symptoms and signs involving the digestive system", "Chapter XVIII", True),
    ("R50.9", "Fever, unspecified", "General symptoms and signs", "Chapter XVIII", True),
    ("R51", "Headache", "General symptoms and signs", "Chapter XVIII", True),
    ("R53.83", "Other fatigue", "General symptoms and signs", "Chapter XVIII", True),
    ("R55", "Syncope and collapse", "General symptoms and signs", "Chapter XVIII", True),
    ("R73.09", "Other abnormal glucose", "Abnormal results of blood chemistry", "Chapter XVIII", True),
    # Chapter XIX — Injury, poisoning
    ("S01.90XA", "Unspecified open wound of unspecified part of head, initial encounter", "Injuries to the head", "Chapter XIX", True),
    ("S52.501A", "Unspecified fracture of the lower end of the right radius, initial encounter for closed fracture", "Injuries to the forearm", "Chapter XIX", True),
    # Chapter XXI — Factors influencing health status (Z-codes)
    ("Z00.00", "Encounter for general adult medical examination without abnormal findings", "Encounters for examinations", "Chapter XXI", False),
    ("Z00.121", "Encounter for routine child health examination with abnormal findings", "Encounters for examinations", "Chapter XXI", False),
    ("Z11.3", "Encounter for screening examination for infections with a predominantly sexual mode of transmission", "Encounters for examination and observation", "Chapter XXI", False),
    ("Z23", "Encounter for immunization", "Encounters for other specific health care", "Chapter XXI", False),
    ("Z79.4", "Long-term (current) use of insulin", "Long-term (current) drug therapy", "Chapter XXI", False),
    ("Z82.49", "Family history of ischaemic heart disease and other diseases of the circulatory system", "Family history of certain disorders", "Chapter XXI", False),
    # India-specific high-burden conditions
    ("A01.0", "Typhoid fever", "Other salmonella infections", "Chapter I", True),
    ("A07.1", "Giardiasis", "Other intestinal diseases due to protozoa", "Chapter I", True),
    ("A27.9", "Leptospirosis, unspecified", "Other spirochaetal diseases", "Chapter I", True),
    ("A91", "Dengue haemorrhagic fever", "Arthropod-borne viral fevers", "Chapter I", True),
    ("B50.9", "Plasmodium falciparum malaria without complication", "Malaria", "Chapter I", True),
    ("B54", "Unspecified malaria", "Malaria", "Chapter I", True),
    ("B19.20", "Unspecified viral hepatitis C without hepatic coma", "Viral hepatitis", "Chapter I", True),
    ("B24", "Human immunodeficiency virus disease", "HIV disease", "Chapter I", True),
    ("E83.3", "Disorders of phosphorus metabolism", "Metabolic disorders", "Chapter IV", True),
    ("I05.9", "Rheumatic mitral valve disease, unspecified", "Rheumatic heart diseases", "Chapter IX", True),
    ("I26.99", "Other pulmonary embolism without acute cor pulmonale", "Pulmonary heart disease", "Chapter IX", True),
    ("J12.89", "Other viral pneumonia", "Influenza and pneumonia", "Chapter X", True),
    ("K11.7", "Disturbances of salivary secretion", "Diseases of oral cavity", "Chapter XI", True),
    ("K50.90", "Crohn's disease of small intestine without complications", "Noninfective enteritis and colitis", "Chapter XI", True),
    ("K51.90", "Ulcerative colitis, unspecified, without complications", "Noninfective enteritis and colitis", "Chapter XI", True),
    ("N17.9", "Acute kidney failure, unspecified", "Acute kidney failure", "Chapter XIV", True),
    ("Q90.9", "Down syndrome, unspecified", "Chromosomal abnormalities", "Chapter XVII", True),
    # Additional common codes
    ("J10.1", "Influenza with other respiratory manifestations, seasonal influenza virus identified", "Influenza and pneumonia", "Chapter X", True),
    ("J11.1", "Influenza with other respiratory manifestations, virus not identified", "Influenza and pneumonia", "Chapter X", True),
    ("Z87.891", "Personal history of other specified conditions", "Personal history of other conditions", "Chapter XXI", False),
    ("R42", "Dizziness and giddiness", "General symptoms and signs", "Chapter XVIII", True),
    ("R00.1", "Bradycardia, unspecified", "Symptoms involving the circulatory and respiratory systems", "Chapter XVIII", True),
    ("L30.9", "Dermatitis, unspecified", "Dermatitis and eczema", "Chapter XII", True),
    ("H10.9", "Unspecified conjunctivitis", "Conjunctival disorders", "Chapter VII", True),
    ("I69.354", "Hemiplegia and hemiparesis following cerebral infarction affecting left non-dominant side", "Sequelae of cerebrovascular diseases", "Chapter IX", True),
    ("M79.10", "Myalgia, unspecified site", "Other soft tissue disorders", "Chapter XIII", True),
    ("M79.89", "Other specified soft tissue disorders", "Other soft tissue disorders", "Chapter XIII", True),
]
# fmt: on


def upgrade() -> None:
    conn = op.get_bind()
    for code, description, category, chapter, is_billable in ICD10_SEED:
        conn.execute(
            text("""
                INSERT INTO icd10_codes (id, code, description, category, chapter, is_billable, created_at, updated_at)
                VALUES (gen_random_uuid(), :code, :description, :category, :chapter, :is_billable, NOW(), NOW())
                ON CONFLICT (code) DO NOTHING
            """),
            {
                "code": code,
                "description": description,
                "category": category,
                "chapter": chapter,
                "is_billable": is_billable,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    codes = [row[0] for row in ICD10_SEED]
    conn.execute(
        text("DELETE FROM icd10_codes WHERE code = ANY(:codes)"),
        {"codes": codes},
    )
