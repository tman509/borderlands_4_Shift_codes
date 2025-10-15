# Requirements Document

## Introduction

The Shift Code Bot is an automated system that discovers, validates, and announces Borderlands Shift Codes to Discord communities. The bot crawls multiple web sources on a schedule, extracts new codes with their metadata (rewards, platforms, expiration), deduplicates against a persistent database, and posts formatted announcements to configured Discord channels. The system prioritizes reliability, politeness to source sites, and clear communication to players.

## Requirements

### Requirement 1: Web Source Discovery and Crawling

**User Story:** As a player who wants timely codes, I want the bot to visit a curated list of web pages and RSS feeds on a schedule, so that new Shift Codes are discovered quickly.

#### Acceptance Criteria

1. WHEN the scheduler triggers THEN the system SHALL fetch each configured source and parse for candidate codes
2. WHEN a page is unreachable THEN the system SHALL retry with exponential backoff and log the failure without stopping the whole run
3. WHEN a source structure changes THEN the system SHALL emit a structured "parse error" alert
4. WHEN a source has multiple pages THEN the system SHALL paginate backward until a configured cutoff date OR until no new codes are found
5. WHEN a page hash hasn't changed since last fetch THEN the parser SHALL be skipped
6. IF a source has pagination THEN backfill runs SHALL NOT re-post previously announced codes

### Requirement 2: Code Parsing and Extraction

**User Story:** As a community manager, I want the bot to extract the code, reward type/platform, and expiration information, so that downstream logic knows what to post.

#### Acceptance Criteria

1. WHEN a page contains a code formatted as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX THEN the system SHALL capture it
2. WHEN text around a code includes expiration phrases THEN the system SHALL store a normalized UTC timestamp
3. IF expiration is not present THEN the system SHALL mark expires_at as null and set is_expiration_estimated as false
4. WHEN primary selector fails THEN the system SHALL use secondary heuristic with regex and context window
5. WHEN both parsing strategies fail THEN the system SHALL emit a parse error with DOM snippet around suspected code location

### Requirement 3: Code Validation and Deduplication

**User Story:** As a developer, I want canonical code representation and reliable deduplication, so that the system maintains data integrity and avoids spam.

#### Acceptance Criteria

1. WHEN a code is parsed THEN the system SHALL normalize it to uppercase, hyphenated, 25-character canonical format
2. WHEN a code has invalid shape THEN the system SHALL discard it with a reason code
3. WHEN a code already exists in database THEN the system SHALL mark as duplicate and NOT enqueue for posting
4. WHEN a new code is discovered THEN the system SHALL insert with first_seen_at, source, reward_type, platform, and expires_at
5. WHEN a code matches existing but has different metadata THEN the system SHALL update metadata and mark as updated
6. WHEN expires_at is less than current time THEN the code SHALL NOT be posted and SHALL be stored with status expired_on_discovery

### Requirement 4: Discord Announcement System

**User Story:** As a Discord community member, I want clear messages with code, reward, platform, and expiration information, so that I can redeem quickly.

#### Acceptance Criteria

1. WHEN a code is deemed new THEN the system SHALL post a single message to configured Discord channels
2. WHEN posting to Discord THEN the message SHALL include code (monospace), reward, platform(s), expiration (UTC & local), and source link
3. WHEN posting multiple messages THEN the system SHALL respect Discord rate limits with queuing and backoff
4. WHEN the same code exists THEN it SHALL NEVER be posted twice to the same channel
5. IF metadata changes meaningfully THEN the system SHALL post a threaded "Update" reply, not a new root message
6. WHEN expires_at is set AND expiration reminders are enabled THEN the system SHALL schedule a one-time reminder message

### Requirement 5: Scheduling and Configuration Management

**User Story:** As a system operator, I want configurable scheduling and source management, so that I can control polling cadence and manage sources without code changes.

#### Acceptance Criteria

1. WHEN configured THEN the system SHALL run on cron-like schedules per environment
2. WHEN manual trigger is requested THEN the system SHALL execute an immediate crawl
3. WHEN managing sources THEN the system SHALL support CRUD operations for URL, type, enabled flag, and parser hints
4. WHEN managing Discord destinations THEN the system SHALL support per-source routing and message templates
5. WHEN configuration changes THEN the system SHALL reload without requiring restart

### Requirement 6: Observability and Monitoring

**User Story:** As a developer, I want structured logs and metrics, so that I can debug issues and measure system performance.

#### Acceptance Criteria

1. WHEN system operates THEN it SHALL log crawl success/failure, parse counts, codes found, duplicates filtered, and posts sent
2. WHEN system operates THEN it SHALL track metrics for crawl latency, parse success rate, post success rate, and time-to-post
3. WHEN N consecutive failures occur for a source THEN the system SHALL send an alert to designated channel
4. WHEN Discord API failures exceed threshold THEN the system SHALL alert with guidance
5. WHEN logging THEN the system SHALL use structured format with appropriate log levels

### Requirement 7: Resilience and Compliance

**User Story:** As a site owner and ecosystem participant, I want the bot to be polite and resilient, so that sources remain accessible and the system handles failures gracefully.

#### Acceptance Criteria

1. WHEN crawling THEN the system SHALL respect robots.txt where applicable
2. WHEN crawling THEN the system SHALL implement per-domain delay and concurrency caps
3. WHEN receiving 429/5xx responses THEN the system SHALL use exponential backoff
4. WHEN storing credentials THEN the system SHALL use environment configuration without hardcoding
5. WHEN displaying times THEN the system SHALL show both UTC and configurable local timezone
6. WHEN handling daylight savings THEN the system SHALL calculate transitions correctly

### Requirement 8: Testing and Quality Assurance

**User Story:** As a developer, I want comprehensive tests, so that regressions are caught automatically and the system remains reliable.

#### Acceptance Criteria

1. WHEN code is committed THEN unit tests SHALL exist for parsing and posting logic
2. WHEN tests run THEN they SHALL use deterministic fixtures for common source pages
3. WHEN CI pipeline runs THEN tests SHALL execute and fail if coverage drops below 80%
4. WHEN deploying THEN an end-to-end smoke test SHALL verify core functionality
5. WHEN testing THEN the system SHALL mock external dependencies appropriately