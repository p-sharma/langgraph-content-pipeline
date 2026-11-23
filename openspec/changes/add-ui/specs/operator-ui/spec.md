# Spec Delta

## Purpose

Gives the single operator a web UI to start a content run, follow its progress, approve or revise its draft, and browse the archive of published posts, without making raw API calls.

## ADDED Requirements

### Requirement: Start a run
The Run page SHALL provide a form with a topic and optional guidance that starts a new run. The UI SHALL reject a topic shorter than 3 characters without calling the API. A successful start SHALL make the new run the current run.

#### Scenario: Valid topic
- **WHEN** the operator submits a topic of at least 3 characters
- **THEN** a new run is created through the API
- **AND** the page shows that run as the current run

#### Scenario: Topic too short
- **WHEN** the operator submits a topic shorter than 3 characters
- **THEN** the page shows a validation message
- **AND** no run is created

#### Scenario: Starting a second run
- **WHEN** a run is already shown and the operator starts another
- **THEN** the new run replaces it as the current run

### Requirement: Current run is addressable by URL
The Run page SHALL carry the current run's ID in its URL. Opening the Run page with a run ID in the URL SHALL show that run, so a page refresh or a UI restart does not lose it.

#### Scenario: Refresh mid-run
- **WHEN** the operator refreshes the browser while a run is shown
- **THEN** the same run is shown again with its current status

#### Scenario: Unknown run ID
- **WHEN** the Run page is opened with a run ID the API does not know
- **THEN** the page says the run was not found and still shows the start form

### Requirement: Live progress while a run is in flight
While the current run is `queued` or `running`, the Run page SHALL refresh the run from the API every few seconds without operator action, and SHALL show its status and a stage hint based on what the run has produced so far.

#### Scenario: Progress updates on its own
- **WHEN** a run is `running` and its sources or draft change in the API
- **THEN** the page shows the new sources or draft within a few seconds, without a manual reload

#### Scenario: Stage hint
- **WHEN** a running run has no sources yet
- **THEN** the hint says it is searching and ranking
- **AND** once sources exist but no draft, the hint says it is researching and drafting
- **AND** once a draft exists, the hint says it is reviewing or revising

### Requirement: Refreshing stops when the run settles
The Run page SHALL stop refreshing automatically once the run's status is anything other than `queued` or `running`.

#### Scenario: Run reaches approval
- **WHEN** a polled run becomes `awaiting_approval`
- **THEN** the page stops refreshing and shows the review

#### Scenario: Run ends
- **WHEN** a polled run becomes `published`, `rejected`, `approved` or `failed`
- **THEN** the page stops refreshing and shows the end state

### Requirement: Review shown while awaiting approval
When the current run is `awaiting_approval`, the Run page SHALL show its review: the draft with citations linked, the numbered references, the critic verdict and note, and the revision count. The run's sources SHALL be viewable on demand.

#### Scenario: Paused run
- **WHEN** the operator opens a run that is `awaiting_approval`
- **THEN** the draft, references, critic verdict, critic note and revision count are shown

### Requirement: Operator decides on the draft
While a run is `awaiting_approval`, the Run page SHALL offer Approve, Request changes and Reject, and SHALL send the chosen decision to the run. Request changes SHALL need non-empty feedback, which the UI SHALL check before calling the API. After a decision is accepted, the page SHALL resume live progress.

#### Scenario: Approve
- **WHEN** the operator clicks Approve
- **THEN** the decision is sent and the page follows the run until it is `published` or `failed`

#### Scenario: Request changes with feedback
- **WHEN** the operator enters feedback and clicks Request changes
- **THEN** the feedback is sent and the page follows the run until it is awaiting approval again with a revised draft

#### Scenario: Request changes without feedback
- **WHEN** the operator clicks Request changes with the feedback box empty
- **THEN** the page asks for feedback and sends nothing

#### Scenario: Reject
- **WHEN** the operator clicks Reject
- **THEN** the decision is sent and the page shows the run as `rejected`

#### Scenario: Run no longer awaiting approval
- **WHEN** the API refuses the decision because the run is busy or not awaiting approval
- **THEN** the page shows a warning and reloads the run's current status

### Requirement: End states are shown
The Run page SHALL show each end state clearly: `published` with a way to view the post, `rejected` and `approved` as final, and `failed` with the run's error message when one exists.

#### Scenario: Published
- **WHEN** the current run is `published`
- **THEN** the page says so and gives access to the published post

#### Scenario: Failed
- **WHEN** the current run is `failed` with an error message
- **THEN** the page shows the error message

### Requirement: Archive of published posts
The Archive page SHALL list published posts newest first, 10 per page, with controls for the previous and next page. Each post SHALL show its topic, publication time, critic verdict and edited flag, and its draft with linked citations and references can be opened.

#### Scenario: Browse posts
- **WHEN** the operator opens the Archive page and posts exist
- **THEN** the newest 10 posts are listed, newest first

#### Scenario: Next page
- **WHEN** more than 10 posts exist and the operator moves to the next page
- **THEN** the next 10 older posts are listed

#### Scenario: No posts
- **WHEN** the operator opens the Archive page and no posts exist
- **THEN** the page says there are no published posts yet

### Requirement: Citations are linked
Wherever the UI shows a draft, each `[n]` citation marker SHALL link to the n-th reference URL, and the references SHALL be listed in order with their numbers.

#### Scenario: Marker with a reference
- **WHEN** a draft containing `[2]` is shown with at least two references
- **THEN** `[2]` links to the second reference URL

#### Scenario: Marker without a reference
- **WHEN** a draft contains a marker whose number has no matching reference
- **THEN** the marker is shown as plain text

### Requirement: Backend errors do not break the page
If the API cannot be reached or returns an unexpected error, the UI SHALL show a short error message and keep the rest of the page usable.

#### Scenario: API down
- **WHEN** the API is unreachable and the operator opens either page
- **THEN** the page shows an error message instead of crashing
