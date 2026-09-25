# AI Log

## 1. Purpose

AI coding tools were used as development assistants during the implementation
of the Document Intake Assistant.

I used AI assistance for implementation, debugging, test generation, and
exploring edge cases. I remained responsible for understanding the WENUP
technical brief, choosing the architecture and technologies, manually testing
the application, identifying incorrect behavior, and deciding which changes
should be applied.

---

## 2. How AI Tools Were Used

AI assistance was mainly used for:

- Project scaffolding and boilerplate
- Backend and frontend implementation
- Groq integration
- MongoDB integration
- Validation and state-transition logic
- Automated test generation
- Debugging and error investigation
- Identifying edge cases
- Code cleanup and review

The generated code was reviewed and tested during development rather than
being accepted without verification.

---

## 3. Initial Planning and Architecture

I first studied the WENUP technical brief and decided on the overall technology
stack and application structure:

- React + Vite for the frontend
- FastAPI for the backend
- Groq for LLM interaction
- MongoDB for persistence
- Pydantic for validation
- Python-based document generation
- Pytest for backend testing

I used AI assistance to create the initial project structure and boilerplate.
I then reviewed the generated structure and guided its implementation according
to the requirements of the technical brief.

---

## 4. Core Implementation

I guided the implementation of:

- Multi-turn conversational intake
- Explicit structured state
- Live structured information display
- Personal Wishes Document preview
- Corrections to previously provided information
- MongoDB persistence
- Groq API integration using Qwen 3.8 27B and strict structured output
- LLM response validation
- Error handling

The main design principle was to keep the structured state separate from the
conversation history so that the confirmed state remains the source of truth.

---

## 5. Manual Testing and Debugging

A significant part of development involved manually testing the application
with different natural-language inputs.

I tested scenarios including:

- Multiple fields provided in one message
- Corrections to previously supplied information
- Adding and removing children
- Adding and removing gifts
- Changing additional wishes
- Duplicate values
- Ambiguous requests
- Explicit "none" responses
- "I don't know" responses
- Invalid or unclear requests
- Provider/API failures

When I found incorrect behavior, I provided the failing conversation or
scenario to the AI tool and used it to investigate the relevant implementation.
I then tested the proposed changes with additional variations.

---

## 6. Important Issues and AI-Assisted Fixes

### Gifts and Wishes

Manual testing exposed problems with gift removal, wish updates, and natural
language variations.

AI assistance was used to investigate the state-transition logic and propose
changes. I then tested the fixes with different forms of:

- Add
- Remove
- Replace
- Clear
- Duplicate
- Ambiguous requests

The final implementation keeps gift and wish operations separate and validates
changes before modifying the structured state.

### Corrections and Multiple Fields

Testing showed that compound messages could sometimes cause information from
one field to be incorrectly associated with another field.

The update flow was revised so that recognized fields and operations are
validated before the state is changed.

This was tested with messages containing multiple fields and corrections in
the same message.

### Groq Rate Limits

During testing, Groq HTTP 429 rate-limit responses were encountered.

AI assistance was used to investigate the issue and improve error handling.
The final behavior preserves the existing structured state when the provider
fails and informs the user that the request should be retried.

The final integration uses `qwen/qwen3.8-27b` as the single primary model. A
normal message makes one LLM request, output is limited to 500 tokens, and the
request includes the current structured state, latest user message, and most
recent assistant turn. The application does not immediately retry or call a
fallback model after HTTP 429. It reads Groq's retry/reset headers and suppresses
additional provider calls during that cooldown.

No state is updated from a failed, rate-limited, or invalid LLM response.

---

## 7. Important Design Decision

An early implementation relied too heavily on conversation history when
determining the current information.

I changed the design so that an explicit validated structured state is the
authoritative source of truth.

The final flow is:

User message
→ LLM interprets the message
→ Structured state transition
→ Backend validation
→ State update
→ MongoDB persistence
→ Document generation

This keeps the LLM responsible for understanding natural language while the
backend remains responsible for state correctness and persistence.

---

## 8. Automated Testing

AI assistance was used to generate and expand automated tests based on the
requirements and failures discovered during manual testing.

The test suite covers:

- Normal field extraction
- Multiple-field messages
- Corrections
- Child additions and removals
- Gift additions and removals
- Wish updates
- Duplicate prevention
- Explicit unknown values
- Clear/none operations
- Ambiguous requests
- Invalid model responses
- Provider failures
- State and document consistency

The final repository contains 15 automated backend tests covering API persistence, state transitions, strict LLM contracts, and provider failures.

---

## 9. Final AI Assistance Summary

AI tools were used as development assistants rather than as the sole decision
maker for the project.

I used AI to:

- Generate and revise implementation code
- Help debug issues
- Generate and expand tests
- Investigate edge cases
- Suggest implementation approaches
- Review code

I was responsible for:

- Understanding the assignment requirements
- Choosing the technology stack
- Guiding the architecture
- Manually testing the application
- Identifying incorrect behavior
- Deciding how the application should behave
- Reviewing proposed changes
- Verifying the final implementation

The final implementation was iteratively tested against the WENUP requirements
and real conversational scenarios.
