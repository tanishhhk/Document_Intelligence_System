// Professions and focus options. IDs match app/services/lenses.py on the API.

export const PROFESSIONS = [
  { id: "student", label: "Student", line: "Revising for exams or writing a thesis", focuses: ["exam", "research"] },
  { id: "professor", label: "Professor", line: "Researching, or preparing lectures", focuses: ["research", "teaching"] },
  {
    id: "employee",
    label: "Working professional",
    line: "Contracts, reports, specs and policies",
    focuses: ["legal", "finance", "engineering", "general"],
  },
];

// strictness: "strict" sticks to the facts; "exam" may explain in its own words.
export const FOCUS = {
  exam: {
    label: "Exam prep",
    line: "Definitions, key facts and what is likely to be asked",
    strictness: "exam",
    questions: ["What are the key definitions?", "What would an exam ask about this?", "Summarise the main points in five lines"],
  },
  research: {
    label: "Research",
    line: "Methods, evidence and stated limitations",
    strictness: "strict",
    questions: ["What question does this document answer?", "What evidence supports the main claim?", "What limitations are mentioned?"],
  },
  teaching: {
    label: "Teaching",
    line: "Core ideas in order, with examples for class",
    strictness: "exam",
    questions: ["What are the core ideas, in order?", "Which examples could I use in class?", "What do students usually get wrong here?"],
  },
  legal: {
    label: "Legal and compliance",
    line: "Obligations, deadlines, conditions and risks",
    strictness: "strict",
    questions: ["What are the obligations and deadlines?", "When can either side end the agreement?", "What penalties or risks are mentioned?"],
  },
  finance: {
    label: "Finance and business",
    line: "Figures, trends, comparisons and risks",
    strictness: "strict",
    questions: ["What are the headline figures?", "What changed compared with the last period?", "What risks are mentioned?"],
  },
  engineering: {
    label: "Engineering and IT",
    line: "Requirements, steps, settings and constraints",
    strictness: "strict",
    questions: ["What are the requirements?", "What are the setup steps?", "What should I check if something fails?"],
  },
  general: {
    label: "HR, operations and other",
    line: "Plain summaries a busy colleague can act on",
    strictness: "exam",
    questions: ["Summarise this in five lines", "What do I need to do?", "What are the important dates?"],
  },
};

export const DEFAULT_QUESTIONS = FOCUS.general.questions;

export function professionOf(id) {
  return PROFESSIONS.find((profession) => profession.id === id);
}

// A focus label inside a sentence: lower case, keeping acronyms such as IT and HR.
export function focusPhrase(id) {
  return FOCUS[id].label.toLowerCase().replace(/\b(it|hr)\b/g, (word) => word.toUpperCase());
}
