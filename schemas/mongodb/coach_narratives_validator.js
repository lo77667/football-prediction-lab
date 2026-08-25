// MongoDB 7+ initialization script for the narrative sidecar.
// `player_id` must match the UUID representation used by PostgreSQL core.player.

db = db.getSiblingDB("youth_soccer_narratives");

const strictValidation = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "note_id", "player_id", "observed_at_utc", "available_at_utc", "author_role",
      "source_type", "provenance", "consent_purpose", "redaction_status", "schema_version"
    ],
    additionalProperties: false,
    properties: {
      _id: { bsonType: "objectId" },
      note_id: { bsonType: "string", minLength: 1 },
      player_id: { bsonType: "string", pattern: "^[0-9a-fA-F-]{36}$" },
      observed_at_utc: { bsonType: "date" },
      available_at_utc: { bsonType: "date" },
      author_role: { bsonType: "string", enum: ["coach", "analyst", "sports_scientist", "safeguarding", "system"] },
      source_type: { bsonType: "string", enum: ["typed_note", "audio_transcript", "development_report", "structured_form"] },
      language: { bsonType: "string", minLength: 2, maxLength: 16 },
      text: { bsonType: "string", minLength: 1 },
      encrypted_object_ref: { bsonType: "string", minLength: 1 },
      transcript_confidence: { bsonType: ["double", "int", "long", "decimal"], minimum: 0, maximum: 1 },
      consent_purpose: { bsonType: "string", enum: ["performance_development", "sports_science", "wellness", "research", "safeguarding"] },
      provenance: {
        bsonType: "object",
        required: ["source_system", "source_record_id", "retrieved_at_utc", "snapshot_sha256"],
        additionalProperties: false,
        properties: {
          source_system: { bsonType: "string", minLength: 1 },
          source_record_id: { bsonType: "string", minLength: 1 },
          source_uri: { bsonType: "string" },
          retrieved_at_utc: { bsonType: "date" },
          snapshot_sha256: { bsonType: "string", pattern: "^[0-9a-f]{64}$" }
        }
      },
      redaction_status: { bsonType: "string", enum: ["pending", "redacted", "reviewed", "restricted", "rejected"] },
      safeguarding_restriction: { bsonType: "bool" },
      reviewer_id: { bsonType: "string" },
      reviewed_at_utc: { bsonType: "date" },
      schema_version: { bsonType: "string", minLength: 1 },
      created_at_utc: { bsonType: "date" },
      updated_at_utc: { bsonType: "date" }
    }
  }
};

const collections = db.getCollectionNames();
if (!collections.includes("coach_notes")) {
  db.createCollection("coach_notes", { validator: strictValidation, validationLevel: "strict", validationAction: "error" });
}

if (!collections.includes("narrative_reports")) {
  db.createCollection("narrative_reports", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["report_id", "player_id", "window_start_utc", "window_end_utc", "author_role", "review_status", "schema_version"],
        additionalProperties: false,
        properties: {
          _id: { bsonType: "objectId" },
          report_id: { bsonType: "string", minLength: 1 },
          player_id: { bsonType: "string", pattern: "^[0-9a-fA-F-]{36}$" },
          window_start_utc: { bsonType: "date" },
          window_end_utc: { bsonType: "date" },
          strengths: { bsonType: "array", items: { bsonType: "string" } },
          development_goals: { bsonType: "array", items: { bsonType: "string" } },
          contextual_factors: { bsonType: "array", items: { bsonType: "string" } },
          source_note_ids: { bsonType: "array", items: { bsonType: "string" } },
          author_role: { bsonType: "string", minLength: 1 },
          review_status: { bsonType: "string", enum: ["draft", "coach_reviewed", "sports_science_reviewed", "safeguarding_restricted", "approved", "rejected"] },
          schema_version: { bsonType: "string", minLength: 1 },
          created_at_utc: { bsonType: "date" },
          updated_at_utc: { bsonType: "date" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}

if (!collections.includes("nlp_annotations")) {
  db.createCollection("nlp_annotations", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["annotation_id", "note_id", "player_id", "taxonomy_version", "model_version", "markers", "review_status", "created_at_utc"],
        additionalProperties: false,
        properties: {
          _id: { bsonType: "objectId" },
          annotation_id: { bsonType: "string", minLength: 1 },
          note_id: { bsonType: "string", minLength: 1 },
          player_id: { bsonType: "string", pattern: "^[0-9a-fA-F-]{36}$" },
          taxonomy_version: { bsonType: "string", minLength: 1 },
          model_version: { bsonType: "string", minLength: 1 },
          language: { bsonType: "string", minLength: 2, maxLength: 16 },
          markers: {
            bsonType: "array",
            items: {
              bsonType: "object",
              required: ["trait", "value", "confidence", "evidence_span", "direction"],
              additionalProperties: false,
              properties: {
                trait: { bsonType: "string", enum: ["confidence", "communication", "coachability", "attention", "recovery_mindset", "competitive_response", "readiness", "other"] },
                value: { bsonType: ["double", "int", "long", "decimal"], minimum: -1, maximum: 1 },
                direction: { bsonType: "string", enum: ["low", "neutral", "high", "mixed", "missing"] },
                confidence: { bsonType: ["double", "int", "long", "decimal"], minimum: 0, maximum: 1 },
                evidence_span: { bsonType: "string", minLength: 1 },
                context: { bsonType: "string" },
                negated: { bsonType: "bool" }
              }
            }
          },
          review_status: { bsonType: "string", enum: ["not_reviewed", "coach_reviewed", "sports_science_reviewed", "rejected"] },
          reviewer_id: { bsonType: "string" },
          reviewed_at_utc: { bsonType: "date" },
          created_at_utc: { bsonType: "date" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}

if (!collections.includes("qualitative_feature_events")) {
  db.createCollection("qualitative_feature_events", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["event_id", "player_id", "trait", "value", "confidence", "observed_at_utc", "available_at_utc", "provenance", "taxonomy_version"],
        additionalProperties: false,
        properties: {
          _id: { bsonType: "objectId" },
          event_id: { bsonType: "string", minLength: 1 },
          player_id: { bsonType: "string", pattern: "^[0-9a-fA-F-]{36}$" },
          note_id: { bsonType: "string" },
          trait: { bsonType: "string", minLength: 1 },
          value: { bsonType: ["double", "int", "long", "decimal"], minimum: -1, maximum: 1 },
          confidence: { bsonType: ["double", "int", "long", "decimal"], minimum: 0, maximum: 1 },
          observed_at_utc: { bsonType: "date" },
          available_at_utc: { bsonType: "date" },
          evidence_ref: { bsonType: "string", minLength: 1 },
          review_status: { bsonType: "string", enum: ["not_reviewed", "coach_reviewed", "sports_science_reviewed", "rejected"] },
          reviewer_id: { bsonType: "string" },
          taxonomy_version: { bsonType: "string", minLength: 1 },
          provenance: { bsonType: "object", required: ["note_id", "source_sha256"], additionalProperties: false, properties: { note_id: { bsonType: "string" }, source_sha256: { bsonType: "string", pattern: "^[0-9a-f]{64}$" } } }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}

if (!collections.includes("ingestion_receipts")) {
  db.createCollection("ingestion_receipts", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["receipt_id", "source_system", "source_record_id", "source_sha256", "received_at_utc", "status"],
        additionalProperties: false,
        properties: {
          _id: { bsonType: "objectId" },
          receipt_id: { bsonType: "string", minLength: 1 },
          source_system: { bsonType: "string", minLength: 1 },
          source_record_id: { bsonType: "string", minLength: 1 },
          source_sha256: { bsonType: "string", pattern: "^[0-9a-f]{64}$" },
          received_at_utc: { bsonType: "date" },
          processed_at_utc: { bsonType: "date" },
          status: { bsonType: "string", enum: ["received", "processed", "quarantined", "failed"] },
          retry_count: { bsonType: ["int", "long"], minimum: 0 },
          error_class: { bsonType: "string" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}

db.coach_notes.createIndex({ note_id: 1 }, { unique: true });
db.coach_notes.createIndex({ player_id: 1, available_at_utc: 1 });
db.coach_notes.createIndex({ player_id: 1, observed_at_utc: 1 });
db.coach_notes.createIndex({ redaction_status: 1, safeguarding_restriction: 1 });
db.narrative_reports.createIndex({ report_id: 1 }, { unique: true });
db.narrative_reports.createIndex({ player_id: 1, window_end_utc: -1 });
db.nlp_annotations.createIndex({ annotation_id: 1 }, { unique: true });
db.nlp_annotations.createIndex({ note_id: 1, model_version: 1 }, { unique: true });
db.qualitative_feature_events.createIndex({ event_id: 1 }, { unique: true });
db.qualitative_feature_events.createIndex({ player_id: 1, available_at_utc: 1, trait: 1 });
db.ingestion_receipts.createIndex({ source_system: 1, source_record_id: 1 }, { unique: true });
db.ingestion_receipts.createIndex({ status: 1, received_at_utc: 1 });
