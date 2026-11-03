-- FINN schema, generated from finn/db.py for sqlite. Do not edit by hand.

CREATE TABLE alert_rules (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	name TEXT NOT NULL, 
	profile VARCHAR(40), 
	symbol VARCHAR(32), 
	kind VARCHAR(16) NOT NULL, 
	direction VARCHAR(8), 
	threshold FLOAT, 
	window INTEGER, 
	categories JSON, 
	min_tier VARCHAR(16), 
	enabled BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	last_evaluated_at DATETIME
);

CREATE INDEX ix_alert_rules_symbol ON alert_rules (symbol);

CREATE TABLE alerts (
	id INTEGER NOT NULL, 
	rule_id INTEGER NOT NULL, 
	dedupe_key VARCHAR(200) NOT NULL, 
	symbol VARCHAR(32) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	session_date VARCHAR(10), 
	announcement_id VARCHAR(64), 
	observed FLOAT, 
	threshold FLOAT, 
	severity VARCHAR(8) NOT NULL, 
	title TEXT NOT NULL, 
	message TEXT NOT NULL, 
	provenance JSON, 
	created_at DATETIME NOT NULL, 
	read BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (dedupe_key)
);

CREATE INDEX ix_alerts_symbol ON alerts (symbol);

CREATE INDEX ix_alerts_rule_id ON alerts (rule_id);

CREATE INDEX ix_alerts_created_at ON alerts (created_at);

CREATE TABLE announcements (
	id VARCHAR(64) NOT NULL, 
	symbol VARCHAR(32) NOT NULL, 
	published_at DATETIME NOT NULL, 
	headline TEXT NOT NULL, 
	subject TEXT NOT NULL, 
	bse_category VARCHAR(120), 
	bse_subcategory VARCHAR(200), 
	attachment_url TEXT, 
	source_url TEXT, 
	category VARCHAR(40) NOT NULL, 
	category_method VARCHAR(16) NOT NULL, 
	base_score INTEGER NOT NULL, 
	reasons JSON, 
	summary TEXT, 
	enrichment JSON, 
	enrichment_status VARCHAR(16) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_announcements_published_at ON announcements (published_at);

CREATE INDEX ix_announcements_symbol ON announcements (symbol);

CREATE TABLE companies (
	symbol VARCHAR(32) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	sector VARCHAR(80) NOT NULL, 
	bse_code VARCHAR(10), 
	in_portfolio BOOLEAN NOT NULL, 
	isin VARCHAR(12), 
	identity_sources JSON, 
	validated_at DATETIME, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (symbol)
);

CREATE TABLE doc_pages (
	doc_id VARCHAR(32) NOT NULL, 
	page INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	PRIMARY KEY (doc_id, page)
);

CREATE TABLE documents (
	id VARCHAR(32) NOT NULL, 
	symbol VARCHAR(32) NOT NULL, 
	kind VARCHAR(24) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	period VARCHAR(40) NOT NULL, 
	url TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	pages INTEGER NOT NULL, 
	error TEXT, 
	retrieved_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_documents_symbol ON documents (symbol);

CREATE TABLE kv (
	"key" VARCHAR(200) NOT NULL, 
	value JSON NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE TABLE llm_calls (
	"key" VARCHAR(64) NOT NULL, 
	model VARCHAR(80) NOT NULL, 
	purpose VARCHAR(60) NOT NULL, 
	response JSON NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	cache_hits INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE TABLE price_bars (
	symbol VARCHAR(32) NOT NULL, 
	date VARCHAR(10) NOT NULL, 
	open FLOAT, 
	high FLOAT, 
	low FLOAT, 
	close FLOAT NOT NULL, 
	volume FLOAT, 
	source VARCHAR(40) NOT NULL, 
	PRIMARY KEY (symbol, date)
);

