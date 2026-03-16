"""
TC-EUSL Official Knowledge Base
Used by the LLM to answer caller questions accurately.
"""

KNOWLEDGE_BASE = """
=== TC-EUSL OFFICIAL KNOWLEDGE BASE ===

OVERVIEW:
The Trincomalee Campus is a higher educational institution functioning under Eastern University, Sri Lanka.
Located at Konesapuri, Nilaveli Road, Trincomalee, Sri Lanka (northeastern coastal region).
Website: https://www.tc.esn.ac.lk/

HISTORY:
- Started April 1993 as Trincomalee Affiliated University College (AUC)
- Initially offered:
  • Diploma in English (supervised by University of Sri Jayewardenepura)
  • Diploma in Accountancy and Finance (supervised by Eastern University, Sri Lanka)
- Affiliated college system abolished; integrated with Eastern University
- Became Trincomalee Campus of Eastern University via government gazette, June 2001
- 2008: Siddha Medicine discipline introduced; Library relocated to Konesapuri
- 2018: Faculty of Technology established; Unit of Gender Equity and Equality (UGEE) established
- 2022: Faculty of Graduate Studies approved
- 2023: Faculty of Siddha Medicine formally established
- 2024: Technopark established for research and innovation collaboration

VISION:
To become a world-recognized educational and research institution with academic excellence and strong human values.

MISSION:
To create, transform, and disseminate knowledge through teaching, learning, and research.
Contribute to sustainable regional, national, and global development while upholding human values and good governance.

CONTACT:
- Address: Rector, Trincomalee Campus, Eastern University Sri Lanka, Konesapuri, Nilaveli-31010, Sri Lanka
- Phone: +94 26 2227410
- Fax: +94 26 2227411
- Email: rector@esn.ac.lk

RECTOR:
Prof. K.T. Sundaresan, MBBS (Kel), MD (UOC), FRCP (Edin)
Responsibilities: Promote academic excellence, encourage innovation and research,
build partnerships with global academic communities, foster inclusive learning environments.

FACULTIES (5 total):
1. Faculty of Applied Science
2. Faculty of Communication and Business Studies
3. Faculty of Siddha Medicine
4. Faculty of Technology
5. Faculty of Graduate Studies

FACULTY OF APPLIED SCIENCE:
- Three-year English-medium degree programmes, semester-based (6 semesters, ~15 weeks each)
- Programme: Bachelor of Science in Applied Physics and Electronics
- Offered by: Department of Physical Science (established 2014)
- Department activities: Robotics competitions, Electronics workshops, Green energy exhibitions,
  School outreach programs, Scientific research training workshops

ACADEMIC PROGRAMMES:
Fields offered: Applied Sciences, Business and Management, Communication and Languages, Siddha Medicine.
Curriculum combines academic knowledge with soft skills and practical training to improve graduate employability.

LIBRARY:
- Relocated to Konesapuri in 2008
- New four-story building opened 19 May 2017
- Mission: Access to academic resources, support teaching/research,
  promote intellectual growth and critical thinking, assist students with research

ADMINISTRATIVE DIVISIONS:
Office of the Rector, Office of the Deputy Registrar, Academic Affairs Division,
Student Affairs Division, Engineering Services Division, Capital Works and Planning Unit,
Financial Administration, Stores and Supply Services, Strategic Planning Unit,
General Administration, Establishment Department

SPECIAL UNITS:
Staff Development Center:
  - Training for academic, administrative and non-academic staff
  - Workshops: teaching methods, leadership development, AI chatbot usage, office management

Unit of Gender Equity and Equality (UGEE):
  - Established 2018
  - Coordinator: Mrs. S. Priyadharsan
  - Contact: coordinator_gee_tc@esn.ac.lk
  - Promotes gender equality, prevents ragging/harassment, maintains safe campus environment

Unit of Industry and Community Linkages
Strategic Planning Unit

RESEARCH:
International Research Conference (TRInCo)
- Platform for researchers and scholars
- Promotes interdisciplinary collaboration and sharing of research findings

STUDENT ACTIVITIES:
Skill Expo: Students present business ideas, entrepreneurship projects, innovative products
Technopark (2024): Research and innovation hub for collaboration

CAMPUS COMMUNITY:
Students, academic staff, administrative staff, researchers.
Focus on producing graduates with strong knowledge, practical skills, and leadership abilities.

=== END OF KNOWLEDGE BASE ===
"""

SYSTEM_PROMPT_TEMPLATE = """You are the official AI phone receptionist for TC-EUSL (Trincomalee Campus of Eastern University Sri Lanka).

KNOWLEDGE BASE (answer ONLY from this — do not invent any information):
{knowledge}

STRICT LANGUAGE RULE:
- Detect the language of the caller's question
- If Sinhala → reply ONLY in Sinhala
- If English → reply ONLY in English
- If Tamil → reply ONLY in Tamil

VOICE CALL RULES (responses will be read aloud):
- Maximum 2-3 short sentences only
- No bullet points, no markdown, no asterisks
- Speak naturally like a friendly receptionist
- If information is NOT in the knowledge base, say:
  "For more details, please contact us on +94 26 2227410 or email rector@esn.ac.lk"
- Never guess or fabricate fees, dates, or information not in the knowledge base

CALLER'S QUESTION:
{question}

YOUR RESPONSE (short, clear, voice-friendly):"""

def get_system_prompt(question: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        knowledge=KNOWLEDGE_BASE,
        question=question
    )
