# content-publishing Specification

## Purpose

Turns a human-approved draft into a stored, permanent post, and reports the run's progress from approval to publication through the run status.

## Requirements

### Requirement: Approved runs are published
When the reviewer approves a draft, the system SHALL record the run as approved and then publish the approved draft as a post, without any further human action.

#### Scenario: Approve leads to a published post
- **WHEN** a run paused for approval is resumed with the `approve` action
- **THEN** a post for that run is stored
- **AND** the run's final status is `published`

#### Scenario: Reject publishes nothing
- **WHEN** a run paused for approval is resumed with the `reject` action
- **THEN** no post is stored for that run
- **AND** the run's final status is `rejected`

#### Scenario: Request changes publishes nothing yet
- **WHEN** a run paused for approval is resumed with the `request_changes` action
- **THEN** no post is stored for that run until a later approval

### Requirement: Post contents
A post SHALL record the run it came from, the topic, the approved draft text with its citation markers, the ordered reference URLs, the publication time, the critic's verdict on the draft, and whether an editor requested changes before approving.

#### Scenario: Post matches what the reviewer approved
- **WHEN** a draft with references is approved and published
- **THEN** the post's draft text and references are exactly those shown to the reviewer at approval
- **AND** the post's critic verdict is one of `passed`, `not_reviewed` or `budget_exhausted`, matching the verdict shown at approval

#### Scenario: Edited flag
- **WHEN** an editor requested changes at least once before the draft was approved
- **THEN** the post is marked as edited

#### Scenario: Unedited flag
- **WHEN** a draft is approved at the first review
- **THEN** the post is not marked as edited

### Requirement: At most one post per run
The system SHALL store at most one post per run, even if the publish step is run more than once for the same run, for example when it is retried after a crash.

#### Scenario: Publish step replayed
- **WHEN** the publish step runs again for a run that already has a post
- **THEN** exactly one post exists for that run
- **AND** the existing post is unchanged
- **AND** the run's final status is `published`

### Requirement: Publication status reporting
The run status SHALL include `published` as an end state. A run approved before publishing existed SHALL keep reporting `approved`.

#### Scenario: Status after publishing
- **WHEN** a client fetches a run whose post was stored
- **THEN** the reported status is `published`

#### Scenario: Run approved before the publisher existed
- **WHEN** a client fetches a run that ended as `approved` with no publish step
- **THEN** the reported status is `approved`

### Requirement: Publish failure is reported
If publishing fails, the system SHALL report the run as `failed` with the error message, and SHALL NOT store a partial post.

#### Scenario: Database unavailable during publish
- **WHEN** the post cannot be stored because the database is unreachable
- **THEN** the run's reported status is `failed`
- **AND** the run's error field describes the failure
- **AND** no post exists for that run
