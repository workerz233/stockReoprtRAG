# Project Delete Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-level delete action that removes the whole project and all derived artifacts after a confirmation prompt.

**Architecture:** Extend the existing project management layer with a whole-project delete method, expose it through a new FastAPI delete route, and add a separate delete button to each project row in the frontend. Reuse the document-delete interaction model so loading, disabled state, confirmation, and refresh behavior stay consistent.

**Tech Stack:** Python, FastAPI, vanilla JavaScript, CSS

---

## Chunk 1: Backend project deletion

### Task 1: Add project deletion support

**Files:**
- Modify: `backend/project_manager.py`
- Modify: `app.py`

- [ ] **Step 1: Check current project lifecycle code**

Inspect `backend/project_manager.py` and `app.py` to follow existing validation and HTTP error mapping patterns.

- [ ] **Step 2: Write the minimal backend implementation**

Add `ProjectManager.delete_project(name)` that validates the name, resolves the existing project root, and removes it recursively. Add `DELETE /api/projects/{project_name}` in `app.py` and map `FileNotFoundError`, `ValueError`, and `RuntimeError` to the same status codes used elsewhere.

- [ ] **Step 3: Verify backend syntax**

Run: `python -m compileall app.py backend`
Expected: all touched Python files compile successfully.

## Chunk 2: Frontend project delete button

### Task 2: Add project delete UI and behavior

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

- [ ] **Step 1: Update project row rendering**

Render each project as a row with a project-select button and a separate delete button so the delete control does not nest inside another button.

- [ ] **Step 2: Add delete state and handler**

Track in-flight project deletions, show a confirmation dialog, call `DELETE /api/projects/{project_name}`, refresh project state, and clear cached project documents for deleted projects.

- [ ] **Step 3: Reuse button styling consistently**

Add project-row layout styles and reuse the existing delete button look for project deletion.

- [ ] **Step 4: Verify frontend syntax**

Run: `node --check frontend/app.js`
Expected: the script parses without syntax errors.

## Chunk 3: Final verification

### Task 3: Validate integrated behavior

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `backend/project_manager.py`
- Modify: `app.py`

- [ ] **Step 1: Re-run targeted verification**

Run: `python -m compileall app.py backend && node --check frontend/app.js`
Expected: both backend and frontend checks pass.

- [ ] **Step 2: Summarize follow-up manual check**

Document that the user can create a project, confirm deletion from the sidebar, and verify that the project disappears from the list.
