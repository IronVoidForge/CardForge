from __future__ import annotations

SCHEMA_VERSION = 5

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      root_path TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      archived_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      set_code TEXT NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      game_mode TEXT NOT NULL DEFAULT 'custom_tcg',
      target_card_count INTEGER NOT NULL DEFAULT 0,
      style_profile_json TEXT NOT NULL DEFAULT '{}',
      rules_profile_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'draft',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, set_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS set_briefs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
      source_prompt TEXT NOT NULL DEFAULT '',
      normalized_brief_json TEXT NOT NULL DEFAULT '{}',
      markdown_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'draft',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_types (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      type_key TEXT NOT NULL,
      display_name TEXT NOT NULL,
      schema_json TEXT NOT NULL,
      template_id TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, type_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS keywords (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      keyword_key TEXT NOT NULL,
      display_name TEXT NOT NULL,
      rules_text TEXT NOT NULL DEFAULT '',
      reminder_text TEXT NOT NULL DEFAULT '',
      allowed_card_types_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, keyword_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS factions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
      faction_key TEXT NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      color_identity_json TEXT NOT NULL DEFAULT '[]',
      style_json TEXT NOT NULL DEFAULT '{}',
      mechanics_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(set_id, faction_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_batches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
      batch_key TEXT NOT NULL,
      request_text TEXT NOT NULL DEFAULT '',
      request_json TEXT NOT NULL DEFAULT '{}',
      target_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'draft',
      raw_response_path TEXT NOT NULL DEFAULT '',
      parsed_json_path TEXT NOT NULL DEFAULT '',
      validation_summary_json TEXT NOT NULL DEFAULT '{}',
      balance_summary_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(set_id, batch_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cards (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
      batch_id INTEGER REFERENCES card_batches(id) ON DELETE SET NULL,
      card_key TEXT NOT NULL,
      name TEXT NOT NULL,
      slug TEXT NOT NULL,
      card_number TEXT NOT NULL DEFAULT '',
      card_type TEXT NOT NULL,
      type_line TEXT NOT NULL DEFAULT '',
      rarity TEXT NOT NULL DEFAULT 'common',
      faction TEXT NOT NULL DEFAULT '',
      cost_json TEXT NOT NULL DEFAULT '{}',
      stats_json TEXT NOT NULL DEFAULT '{}',
      rules_text TEXT NOT NULL DEFAULT '',
      flavor_text TEXT NOT NULL DEFAULT '',
      keywords_json TEXT NOT NULL DEFAULT '[]',
      mechanics_json TEXT NOT NULL DEFAULT '[]',
      design_notes TEXT NOT NULL DEFAULT '',
      art_direction TEXT NOT NULL DEFAULT '',
      template_id TEXT NOT NULL DEFAULT '',
      back_template_id TEXT NOT NULL DEFAULT 'default_card_back_v1',
      status TEXT NOT NULL DEFAULT 'draft',
      current_version_id INTEGER,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(set_id, card_key),
      UNIQUE(set_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_versions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
      version_number INTEGER NOT NULL,
      source TEXT NOT NULL,
      name TEXT NOT NULL,
      type_line TEXT NOT NULL DEFAULT '',
      cost_json TEXT NOT NULL DEFAULT '{}',
      stats_json TEXT NOT NULL DEFAULT '{}',
      rules_text TEXT NOT NULL DEFAULT '',
      flavor_text TEXT NOT NULL DEFAULT '',
      keywords_json TEXT NOT NULL DEFAULT '[]',
      mechanics_json TEXT NOT NULL DEFAULT '[]',
      design_notes TEXT NOT NULL DEFAULT '',
      art_direction TEXT NOT NULL DEFAULT '',
      change_reason TEXT NOT NULL DEFAULT '',
      raw_payload_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(card_id, version_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
      set_id INTEGER REFERENCES sets(id) ON DELETE SET NULL,
      card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
      batch_id INTEGER REFERENCES card_batches(id) ON DELETE SET NULL,
      task_type TEXT NOT NULL,
      model TEXT NOT NULL,
      temperature REAL NOT NULL DEFAULT 0,
      max_tokens INTEGER,
      system_prompt_path TEXT NOT NULL DEFAULT '',
      user_prompt_path TEXT NOT NULL DEFAULT '',
      raw_response_path TEXT NOT NULL DEFAULT '',
      parsed_response_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'planned',
      error_message TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_templates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      template_key TEXT NOT NULL,
      name TEXT NOT NULL,
      task_type TEXT NOT NULL,
      prompt_format_json TEXT NOT NULL DEFAULT '{}',
      system_template TEXT NOT NULL DEFAULT '',
      user_template TEXT NOT NULL DEFAULT '',
      output_contract TEXT NOT NULL DEFAULT '',
      markdown_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, template_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_template_versions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      template_key TEXT NOT NULL,
      version_number INTEGER NOT NULL,
      version_key TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'manual',
      source_target_type TEXT NOT NULL DEFAULT '',
      source_target_id TEXT NOT NULL DEFAULT '',
      markdown_path TEXT NOT NULL DEFAULT '',
      summary TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, template_key, version_number),
      UNIQUE(project_id, version_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lab_promotion_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      request_key TEXT NOT NULL,
      lab_type TEXT NOT NULL,
      case_key TEXT NOT NULL,
      run_key TEXT NOT NULL DEFAULT '',
      template_key TEXT NOT NULL DEFAULT '',
      target_type TEXT NOT NULL DEFAULT '',
      target_id TEXT NOT NULL DEFAULT '',
      proposal_markdown_path TEXT NOT NULL DEFAULT '',
      evidence_json_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'requested',
      review_item_id INTEGER REFERENCES review_items(id) ON DELETE SET NULL,
      applied_version_key TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, request_key)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS prompt_packages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      set_id INTEGER REFERENCES sets(id) ON DELETE SET NULL,
      card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
      batch_id INTEGER REFERENCES card_batches(id) ON DELETE SET NULL,
      package_key TEXT NOT NULL,
      task_type TEXT NOT NULL,
      template_key TEXT NOT NULL,
      package_markdown_path TEXT NOT NULL DEFAULT '',
      system_prompt_path TEXT NOT NULL DEFAULT '',
      user_prompt_path TEXT NOT NULL DEFAULT '',
      input_payload_json TEXT NOT NULL DEFAULT '{}',
      output_contract_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'rendered',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, package_key)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS prompt_lab_cases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      case_key TEXT NOT NULL,
      template_key TEXT NOT NULL,
      task_type TEXT NOT NULL DEFAULT '',
      target_type TEXT NOT NULL DEFAULT '',
      target_id TEXT NOT NULL DEFAULT '',
      case_dir TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      accepted_run_key TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, case_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_lab_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES prompt_lab_cases(id) ON DELETE CASCADE,
      run_key TEXT NOT NULL,
      variant_label TEXT NOT NULL DEFAULT '',
      candidate_prompt_path TEXT NOT NULL DEFAULT '',
      raw_response_path TEXT NOT NULL DEFAULT '',
      parsed_response_json TEXT NOT NULL DEFAULT '{}',
      metrics_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'unreviewed',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(case_id, run_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS image_lab_cases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
      case_key TEXT NOT NULL,
      mode TEXT NOT NULL DEFAULT 'card_art',
      target_type TEXT NOT NULL DEFAULT 'card',
      target_id TEXT NOT NULL DEFAULT '',
      case_dir TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      accepted_attempt_key TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, case_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS image_lab_attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES image_lab_cases(id) ON DELETE CASCADE,
      attempt_key TEXT NOT NULL,
      prompt_markdown_path TEXT NOT NULL DEFAULT '',
      candidate_manifest_path TEXT NOT NULL DEFAULT '',
      review_json_path TEXT NOT NULL DEFAULT '',
      comparison_json_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'unreviewed',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(case_id, attempt_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generation_jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      job_type TEXT NOT NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      priority INTEGER NOT NULL DEFAULT 100,
      attempt_count INTEGER NOT NULL DEFAULT 0,
      max_attempts INTEGER NOT NULL DEFAULT 3,
      payload_json TEXT NOT NULL DEFAULT '{}',
      result_json TEXT NOT NULL DEFAULT '{}',
      error_message TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      started_at TEXT,
      completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comfy_workflows (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      workflow_key TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      workflow_path TEXT NOT NULL,
      supported_job_type TEXT NOT NULL,
      patch_points_json TEXT NOT NULL DEFAULT '{}',
      default_settings_json TEXT NOT NULL DEFAULT '{}',
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comfy_jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      generation_job_id INTEGER REFERENCES generation_jobs(id) ON DELETE SET NULL,
      workflow_id INTEGER REFERENCES comfy_workflows(id) ON DELETE SET NULL,
      prompt_id TEXT NOT NULL DEFAULT '',
      seed INTEGER,
      positive_prompt TEXT NOT NULL DEFAULT '',
      negative_prompt TEXT NOT NULL DEFAULT '',
      settings_json TEXT NOT NULL DEFAULT '{}',
      patched_workflow_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'planned',
      submitted_at TEXT,
      completed_at TEXT,
      error_message TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS art_prompts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
      version_number INTEGER NOT NULL,
      positive_prompt TEXT NOT NULL,
      negative_prompt TEXT NOT NULL DEFAULT '',
      prompt_json TEXT NOT NULL DEFAULT '{}',
      prompt_markdown_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'draft',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS art_candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
      art_prompt_id INTEGER REFERENCES art_prompts(id) ON DELETE SET NULL,
      comfy_job_id INTEGER REFERENCES comfy_jobs(id) ON DELETE SET NULL,
      candidate_key TEXT NOT NULL,
      image_path TEXT NOT NULL,
      thumbnail_path TEXT NOT NULL DEFAULT '',
      seed INTEGER,
      workflow_key TEXT NOT NULL DEFAULT '',
      settings_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'generated',
      review_status TEXT NOT NULL DEFAULT 'open',
      score_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(card_id, candidate_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS templates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      template_key TEXT NOT NULL,
      name TEXT NOT NULL,
      template_type TEXT NOT NULL,
      card_type TEXT NOT NULL DEFAULT '',
      canvas_width INTEGER NOT NULL,
      canvas_height INTEGER NOT NULL,
      template_json TEXT NOT NULL,
      preview_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(project_id, template_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS renders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
      card_version_id INTEGER REFERENCES card_versions(id) ON DELETE SET NULL,
      art_candidate_id INTEGER REFERENCES art_candidates(id) ON DELETE SET NULL,
      template_id INTEGER REFERENCES templates(id) ON DELETE SET NULL,
      render_key TEXT NOT NULL,
      front_path TEXT NOT NULL DEFAULT '',
      back_path TEXT NOT NULL DEFAULT '',
      preview_path TEXT NOT NULL DEFAULT '',
      print_path TEXT NOT NULL DEFAULT '',
      layout_report_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'rendered',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(card_id, render_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      set_id INTEGER REFERENCES sets(id) ON DELETE SET NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      review_type TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      preview_path TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      severity TEXT NOT NULL DEFAULT 'normal',
      assigned_to TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      review_item_id INTEGER NOT NULL REFERENCES review_items(id) ON DELETE CASCADE,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      decision TEXT NOT NULL,
      reason TEXT NOT NULL DEFAULT '',
      tags_json TEXT NOT NULL DEFAULT '[]',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rework_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      source_review_item_id INTEGER REFERENCES review_items(id) ON DELETE SET NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      rework_type TEXT NOT NULL,
      reason TEXT NOT NULL DEFAULT '',
      operator_notes TEXT NOT NULL DEFAULT '',
      failure_tags_json TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'requested',
      result_target_type TEXT NOT NULL DEFAULT '',
      result_target_id TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auto_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      set_id INTEGER REFERENCES sets(id) ON DELETE SET NULL,
      card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      review_type TEXT NOT NULL,
      auto_status TEXT NOT NULL,
      score_100 INTEGER NOT NULL DEFAULT 0,
      findings_json TEXT NOT NULL DEFAULT '[]',
      recommendations_json TEXT NOT NULL DEFAULT '[]',
      report_json_path TEXT NOT NULL DEFAULT '',
      report_markdown_path TEXT NOT NULL DEFAULT '',
      source_model TEXT NOT NULL DEFAULT 'offline_heuristic',
      status TEXT NOT NULL DEFAULT 'completed',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
      export_type TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'planned',
      settings_json TEXT NOT NULL DEFAULT '{}',
      output_path TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      completed_at TEXT,
      error_message TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
      event_type TEXT NOT NULL,
      target_type TEXT NOT NULL DEFAULT '',
      target_id TEXT NOT NULL DEFAULT '',
      payload_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]
