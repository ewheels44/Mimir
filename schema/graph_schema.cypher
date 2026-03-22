// Kuzu Graph Schema for Three-Layer AI Context System
// T3: Graph Schema Definition

// ============================================
// NODE TABLES
// ============================================

CREATE NODE TABLE BusinessGoal(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE Feature(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE Module(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE DataModel(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE RevenueStream(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE Risk(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE CustomerSegment(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

CREATE NODE TABLE ExternalDep(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    metadata JSON
);

// ============================================
// EDGE TABLES
// ============================================

// Feature implements BusinessGoal
CREATE REL TABLE implements(
    FROM Feature TO BusinessGoal,
    MANY_MANY,
    reverse_label="implemented_by"
);

// Module depends on Module (dependency chain)
CREATE REL TABLE depends_on(
    FROM Module TO Module,
    MANY_MANY,
    reverse_label="depended_on_by"
);

// Feature depends on Feature
CREATE REL TABLE depends_on_feature(
    FROM Feature TO Feature,
    MANY_MANY,
    reverse_label="depended_on_by"
);

// Module depends on DataModel
CREATE REL TABLE depends_on_data(
    FROM Module TO DataModel,
    MANY_MANY,
    reverse_label="data_provided_by"
);

// Feature enables Feature
CREATE REL TABLE enables(
    FROM Feature TO Feature,
    MANY_MANY,
    reverse_label="enabled_by"
);

// Module enables Feature
CREATE REL TABLE enables_feature(
    FROM Module TO Feature,
    MANY_MANY,
    reverse_label="enabled_by"
);

// Risk blocks Feature
CREATE REL TABLE blocks(
    FROM Risk TO Feature,
    MANY_MANY,
    reverse_label="blocked_by"
);

// Risk blocks Module
CREATE REL TABLE blocks_module(
    FROM Risk TO Module,
    MANY_MANY,
    reverse_label="blocked_by"
);

// Feature serves CustomerSegment
CREATE REL TABLE serves(
    FROM Feature TO CustomerSegment,
    MANY_MANY,
    reverse_label="served_by"
);

// RevenueStream serves CustomerSegment
CREATE REL TABLE serves_segment(
    FROM RevenueStream TO CustomerSegment,
    MANY_MANY,
    reverse_label="served_by"
);

// Feature requires Module
CREATE REL TABLE requires(
    FROM Feature TO Module,
    MANY_MANY,
    reverse_label="required_by"
);

// Feature requires DataModel
CREATE REL TABLE requires_data(
    FROM Feature TO DataModel,
    MANY_MANY,
    reverse_label="required_by"
);

// Feature requires ExternalDep
CREATE REL TABLE requires_external(
    FROM Feature TO ExternalDep,
    MANY_MANY,
    reverse_label="required_by"
);

// BusinessGoal measured_by RevenueStream
CREATE REL TABLE measured_by(
    FROM BusinessGoal TO RevenueStream,
    MANY_MANY,
    reverse_label="measures"
);

// BusinessGoal funded_by RevenueStream
CREATE REL TABLE funded_by(
    FROM BusinessGoal TO RevenueStream,
    MANY_MANY,
    reverse_label="funds"
);