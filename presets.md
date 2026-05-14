# Word Play Presets Reference

This file mirrors `src/word_play/presets` and summarizes each preset module, plus the top-level classes and functions it defines, so future environment work can reuse the existing building blocks faster.

## Preset Usage Rules

- Prefer preset classes, actions, and components directly before writing custom code.
- If a mechanic can be expressed with a preset, use the preset.
- When using a preset, do not alias it behind a wrapper, rename, or helper unless there is a strong reason.
- Only write custom actions or components for the parts that are truly environment-specific.

## Filesystem View

```text
src/word_play/presets/
├── action_policies
│   ├── follow_action_sequence.py
│   ├── human.py
│   ├── llm_action_and_communication.py
│   └── random_policy.py
├── environments
│   ├── __init__.py
│   ├── simple_2d_grid_world.py
│   └── simple_env_reset_mixin.py
├── models
│   ├── __init__.py
│   ├── human.py
│   ├── model.py
│   ├── openrouter.py
│   └── registry.py
├── movement
│   ├── __init__.py
│   ├── common.py
│   ├── simple_1d_grid.py
│   ├── simple_2d_grid.py
│   └── single_point.py
├── observation
│   ├── __init__.py
│   ├── simple_observation.py
│   └── utils.py
├── renderers
│   ├── __init__.py
│   ├── assets.py
│   ├── draw.py
│   ├── interactive_env.py
│   ├── layout.py
│   ├── layout_room_graph.py
│   ├── pygame_env_tools.py
│   ├── renderer.py
│   ├── replay_and_live.py
│   ├── runtime.py
│   └── wall_geometry.py
├── systems
│   ├── communication
│   │   ├── chat_room_action_communication
│   │   │   ├── presets
│   │   │   │   └── policies.py
│   │   │   ├── __init__.py
│   │   │   └── core.py
│   │   ├── trade_communication
│   │   │   ├── presets
│   │   │   │   └── policies.py
│   │   │   ├── __init__.py
│   │   │   ├── core.py
│   │   │   └── trade_actions.py
│   │   ├── __init__.py
│   │   └── core.py
│   ├── __init__.py
│   ├── action_compositions.py
│   ├── combat.py
│   ├── containers.py
│   ├── cooldown.py
│   ├── crafter.py
│   ├── currency.py
│   ├── delivery.py
│   ├── destructible.py
│   ├── do_nothing.py
│   ├── freezable.py
│   ├── health.py
│   ├── inventory.py
│   ├── ownership.py
│   ├── preferences.py
│   ├── regrowable.py
│   ├── reward.py
│   ├── team_marker.py
│   └── zap.py
├── __init__.py
├── action_args.py
├── action_validations.py
├── entity_orderings.py
└── reward_functions.py
```

## Module Guide

### Top Level

#### `__init__.py`
- Purpose: Curated preset import surface.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `action_args.py`
- Purpose: Typed action-argument presets plus reusable validator helpers for action kwargs.
- Class `Int_Arg`: Integer action argument with optional validation constraints.
- Function `arg_in_range`: Build a validator that accepts numeric values inside a closed interval.
- Class `Int_Range_Arg`: Argument that parses a bounded integer range value.
- Class `Float_Arg`: Floating-point action argument with optional validation constraints.
- Class `Bool_Arg`: Boolean action argument preset.
- Class `String_Arg`: Free-form string action argument preset.
- Function `arg_matches_regex`: Build a validator that accepts strings matching a regex.
- Class `Regex_String_Arg`: String argument constrained by a regular-expression pattern.
- Function `arg_in_set`: Build a validator that accepts values from a fixed set.
- Class `Choice_Arg`: Base preset for arguments chosen from a predefined option set.
- Class `String_Choice_Arg`: Choice argument specialized for string options.
- Class `Int_Choice_Arg`: Choice argument specialized for integer options.
- Function `arg_in_choice_fn_result`: Build a validator that checks membership against dynamically generated choices.
- Class `Dynamic_Choice_Arg`: Choice argument whose valid options are computed at runtime.
- Class `List_Arg`: List-valued action argument preset.
- Class `Dict_Arg`: Dictionary-valued action argument preset.

#### `action_validations.py`
- Purpose: Reusable target validators for tags and attached components.
- Class `Target_Has_Tag`: Validation rule requiring the target entity to carry a given tag.
- Class `Target_Doesnt_Have_Tag`: Validation rule requiring the target entity to not carry a given tag.
- Class `Target_Has_Component`: Validation rule requiring the target entity to have a component type attached.

#### `entity_orderings.py`
- Purpose: Helper functions for deciding entity iteration order each step.
- Function `entity_definition_order`: Return entities in their original definition order.
- Function `random_order`: Shuffle a collection into a randomized execution order.
- Function `randomize_agent_order`: Randomize just the agent subset while preserving non-agent placement rules.

#### `reward_functions.py`
- Purpose: Tiny reward-function presets that plug into environments.
- Function `zero_reward_func`: Reward callback that always returns zero.

### Action Policies

#### `action_policies/follow_action_sequence.py`
- Purpose: Preset module in the Word Play preset library.
- Function `matching_actions`: Return all `Action_Selection` objects whose action and target match the requested filters.
- Class `Follow_Action_Sequence`: Policy that repeatedly walks an entity through a scripted action sequence.

#### `action_policies/human.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Human_Takes_Action`: Policy that prompts a real person to choose the entity action.

#### `action_policies/llm_action_and_communication.py`
- Purpose: Preset module in the Word Play preset library.
- Class `LLM_Action_And_Communication_Policy`: A combined action-selection and communication policy backed by any `Model`.

#### `action_policies/random_policy.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Random_Policy`: Policy that picks a random valid action from the current observation.

### Environments

#### `environments/__init__.py`
- Purpose: Environment preset namespace for ready-made environment shells and reset helpers.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `environments/simple_2d_grid_world.py`
- Purpose: Concrete environment preset for tile-based multi-entity grid worlds.
- Class `Simple_2D_Grid_World`: Environment preset that coordinates entities, movement, stepping, and resets on a 2D grid.

#### `environments/simple_env_reset_mixin.py`
- Purpose: Mixin that gives simple environments a configurable reset/build cycle.
- Class `Simple_Env_Reset_Mixin`: Shared reset/build helper for presets that reconstruct entity state from a simple spec.

### Models

#### `models/__init__.py`
- Purpose: Model preset namespace collecting chat model adapters and registry helpers.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `models/human.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Human_Model`: Replaces the LLM with a human typing responses.

#### `models/model.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Chat_Message`: Structured chat message record shared by model adapters.
- Function `normalize_chat_messages`: Normalize chat-message inputs into the standard message structure.
- Class `Model`: Provider-agnostic model interface.

#### `models/openrouter.py`
- Purpose: Preset module in the Word Play preset library.
- Class `OpenRouter_Model`: Chat model backed by OpenRouter, or any OpenAI-compatible endpoint configured through `base_url`.

#### `models/registry.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Model_Registry`: Central registry for models.
- Function `register_model`: Register a model factory or adapter under a lookup name.
- Function `resolve_registered_model`: Resolve a registered model name into an instantiated model adapter.

### Movement

#### `movement/__init__.py`
- Purpose: Movement preset namespace collecting common position components and move actions.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `movement/common.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Collidable`: Component marking an entity as participating in collision checks.
- Function `positions_are_close_if_equal`: Treat two positions as adjacent only when they are exactly equal.
- Function `check_for_collision_at_position`: Test whether a collidable entity already occupies a candidate position.
- Class `No_Collision_Will_Occur`: Generic collision validator for movement actions that only mutate the actor's position.

#### `movement/simple_1d_grid.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Position_1D`: Single-axis position component for line-based worlds.

#### `movement/simple_2d_grid.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Position_2D`: Grid position component storing `x`/`y` coordinates.
- Class `No_Collision_Will_Occur_Left`: Left-move validator that blocks collisions before movement.
- Class `No_Collision_Will_Occur_Right`: Right-move validator that blocks collisions before movement.
- Class `No_Collision_Will_Occur_Up`: Up-move validator that blocks collisions before movement.
- Class `No_Collision_Will_Occur_Down`: Down-move validator that blocks collisions before movement.
- Class `Move_Left`: Action preset that moves an entity one tile left.
- Class `Move_Right`: Action preset that moves an entity one tile right.
- Class `Move_Up`: Action preset that moves an entity one tile up.
- Class `Move_Down`: Action preset that moves an entity one tile down.

#### `movement/single_point.py`
- Purpose: Preset module in the Word Play preset library.
- Class `Single_Point_Position`: Position component for worlds where every entity shares one abstract location.

### Observation

#### `observation/__init__.py`
- Purpose: Observation preset namespace centered on the default text observation builder.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `observation/simple_observation.py`
- Purpose: Preset module in the Word Play preset library.
- Function `format_action_list`: Render possible actions into compact observation text.
- Function `format_action_details`: Render richer action details, args, and target hints for observations.
- Class `Simple_Observation`: Default text observation builder for describing self, nearby entities, and actions.

#### `observation/utils.py`
- Purpose: Preset module in the Word Play preset library.
- Function `format_possible_actions`: Format possible actions for display in an observation payload.
- Function `component_data_attributes`: Extract printable component fields for observation formatting.
- Function `entity_state_to_str_with_complete_info`: Render a detailed entity summary including full component data.
- Function `entity_state_to_str`: Render a shorter entity summary for ordinary observations.
- Function `indent`: Indent multiline strings for nested observation blocks.
- Function `format_nearby_entities`: Render the nearby-entity portion of an observation.

### Renderers

#### `renderers/__init__.py`
- Purpose: Renderer preset namespace that re-exports the pygame rendering surface and helpers.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `renderers/assets.py`
- Purpose: Preset module in the Word Play preset library.
- Function `candidate_asset_paths`: Return the filesystem locations to try for a sprite or asset name.
- Function `get_or_load_image`: Load a sprite once and reuse it from the renderer cache.
- Function `get_scaled_image`: Load and cache a sprite scaled to the requested dimensions.
- Function `resolve_wall_sprite`: Choose the best wall sprite variant for a tile based on neighbors.

#### `renderers/draw.py`
- Purpose: Preset module in the Word Play preset library.
- Function `visible_renderables`: Collect visible renderable entities sorted by draw order.
- Function `background_items`: Fetch and normalize background tiles from the active layout adapter.
- Function `entity_health_value`: Read an entity's health value from any health-like component.
- Function `entity_max_health_value`: Read an entity's max-health value from any health-like component.
- Function `title_case_name`: Convert snake/camel-ish names into short label text.
- Function `entity_inventory_entries`: Return inventory entries with names, counts, and sprite hints for the inspector card.
- Function `component_stat_pairs`: Derive quantifiable status stats from the entity state.
- Function `entity_primary_stats`: Return compact key/value pairs for the floating entity card.
- Function `selected_card_metrics`: Derive selected-entity card sizing from a shared tile-based scale.
- Function `selected_entity`: Return the entity currently selected in the renderer, if it still exists.
- Function `update_damage_flash_state`: Track recent health drops so damaged entities can flash briefly.
- Function `entity_world_position`: Return an entity's tile position in renderer world coordinates.
- Function `update_camera_state`: Choose visible tile bounds from either full-map or focused camera mode.
- Function `is_within_visible_bounds`: Report whether a tile lies inside the active camera window.
- Function `visible_tile_set`: Return line-of-sight tiles when a focused agent is being inspected.
- Function `flash_tinted_surface`: Return a tinted copy of a sprite for temporary visual effects.
- Function `animated_sprite_name`: Choose the active sprite frame for a renderable.
- Function `interpolated_entity_screen_position`: Get the current on-screen entity position used for drawing.
- Function `draw_focus_ring`: Highlight the focused agent so camera mode is visually obvious.
- Function `draw_selection_ring`: Highlight the selected entity so inspection is visually anchored.
- Function `draw_selected_entity_card`: Draw a floating inspector card above the selected entity.
- Function `draw_emissive_glow`: Add a soft glow behind emissive sprites and props.
- Function `blit_scaled_sprite`: Load, scale, and draw a sprite at a tile with the chosen anchor.
- Function `draw_wall_sprite`: Draw a wall tile using the best matching sprite variant.
- Function `draw_wall_background_tile`: Draw a wall background tile from its sprite set.
- Function `draw_entity_items`: Draw items as overlays on an entity using flexible layouts.
- Function `draw_entity`: Draw an entity sprite, including damage flash and optional overlay.
- Function `draw_hit_effects`: Draw transient hit-effect sprites centered on affected entities.
- Function `draw_background_tile`: Draw one background tile and require explicit sprite-backed assets.
- Function `draw_grid_overlay`: Draw grid lines over the world area for debugging or readability.
- Function `draw_visibility_mask`: Darken tiles outside the active sight radius to visualize limited perception.
- Function `draw_hud_panel`: Render the bottom HUD panel with step counter, mode, and controls.
- Function `draw_sidebar_panel`: Render an optional right-hand sidebar with agent observations and options.
- Function `draw_end_overlay`: Draw a centered overlay when the environment reaches a terminal state.
- Function `draw_world_vignette`: Apply a subtle darkening toward the edges of the world view.
- Function `wrap_text_lines`: Wrap text greedily into lines that fit within the given width.
- Function `fit_wrapped_text_lines`: Choose a font and wrapped lines that fit within speech-bubble limits.
- Function `collect_speech_bubbles`: Collect speech bubbles from the environment or renderable components.
- Function `parse_trade_message`: Parse the compact renderer trade-message format into structured fields.
- Function `draw_trade_bubble`: Draw a trade window above the trading agent.
- Function `draw_speech_bubbles`: Draw speech bubbles above entities with rounded boxes and tails.
- Function `auto_tile_wall_entities`: Update `sprite_path` for wall entities based on neighbor auto-tiling.
- Function `render_environment`: Render a full frame including background, entities, effects, and HUD.

#### `renderers/interactive_env.py`
- Purpose: Preset module in the Word Play preset library.
- Function `default_experiment_log_path`: Return the default filesystem path for a new experiment recording.
- Function `newest_experiment_log_path`: Find the most recent experiment log for a given run family.
- Function `_json_safe`: Convert nested values into JSON-serializable shapes for recordings.
- Function `serialize_action_selection`: Convert one action selection into recording-safe data.
- Function `serialize_observation`: Convert an observation payload into recording-safe data.
- Function `capture_environment_frame`: Capture one environment frame for replay or debugging.
- Class `ExperimentRecorder`: Helper that buffers and saves replay or experiment frames.
- Class `InteractiveEnvironmentSession`: Stateful controller for a human-driven interactive environment session.
- Function `load_recording_payload`: Load a pickled replay payload from disk.

#### `renderers/layout.py`
- Purpose: Preset module in the Word Play preset library.
- Function `_is_in_any_inventory`: Check if an item is in any entity's inventory.
- Function `_is_in_closed_container`: Check if an item is in a hidden or closed container.
- Class `Position_Layout_Adapter`: Map environment positions and optional backgrounds into render space.
- Class `Grid_Layout_Adapter`: Use entity `x`/`y` values directly as grid coordinates.
- Function `_get_slot_offsets`: Return predefined visual offsets for `n` entities at a single point.
- Class `SinglePointLayout`: Unified layout for entities at a single-point position.
- Class `Graph_Layout_Adapter`: Layout adapter for graph-based environments.
- Class `Continuous_2D_Layout_Adapter`: Adapter for continuous 2D positions with camera support.
- Class `Environment_Layout_Adapter`: Grid layout that fetches background tiles from env or renderer.

#### `renderers/layout_room_graph.py`
- Purpose: Room-based graph layout adapter that renders rooms as quadrilaterals.
- Class `Room_Graph_Layout_Adapter`: Layout adapter for room-based graph environments.

#### `renderers/pygame_env_tools.py`
- Purpose: Preset module in the Word Play preset library.
- Function `_apply_replay_hud`: Attach replay HUD text before rendering a recorded frame.
- Function `run_overcooked_replay`: Launch a replay viewer tuned for the Overcooked-style example environments.
- Function `_selection_lines`: Format selected-entity details for the HUD sidebar.
- Function `_collect_required_kwargs`: Collect unresolved required action args from the current choices.
- Function `run_interactive_overcooked`: Launch an interactive live viewer for Overcooked-style example environments.
- Function `_build_cli`: Build the command-line parser for the pygame environment tools entrypoint.
- Function `main`: CLI entrypoint for the pygame environment tools module.

#### `renderers/renderer.py`
- Purpose: Preset module in the Word Play preset library.
- Class `LLMConfig`: Configuration for LLM mode.
- Class `Renderable`: Store sprite and overlay metadata for an entity.
- Class `Renderer`: Abstract renderer base class for environment visualization backends.
- Class `Pygame_Renderer`: Concrete renderer that delegates drawing to pygame helpers.

#### `renderers/replay_and_live.py`
- Purpose: Preset module in the Word Play preset library.
- Class `RunSessionConfig`: Unified configuration for running a rendered session.
- Function `run_session`: Run a rendered session with unified configuration.
- Function `_build_phase_step_builder`: Build a step builder that alternates between discuss and act phases.
- Function `run_exp`: Run an experiment with pygame rendering.
- Class `ReplayFrameEnvironment`: Rebuild a minimal environment object from a recorded frame snapshot.
- Function `selection_label`: Format a recorded action selection for HUD notes and logs.
- Function `prompt_options_for_arg`: Build numbered pygame prompt options for a required action argument.
- Function `build_pending_prompt`: Queue unresolved required kwargs before a live step can run.
- Function `active_prompt_entry`: Return the current required-argument prompt being shown to the user.
- Function `apply_prompt_choice`: Apply one prompt choice and report whether the prompt queue is finished.
- Function `apply_live_hud`: Populate HUD text for live stepping and required-input prompts.
- Function `apply_replay_hud`: Inject replay-specific HUD text into a recorded frame payload.
- Function `handle_entity_click`: Select the clicked entity and focus agents; clear selection on empty-space clicks.
- Function `capture_frame`: Capture the current environment as a serializable replay frame.
- Function `record_frame`: Append one captured frame to memory and optionally flush it to disk.
- Function `step_and_record`: Advance the environment one step and record the resulting frame.
- Function `make_recorder`: Create an experiment recorder unless logging has been disabled.
- Function `episode_done`: Return whether every agent has terminated or truncated the episode.
- Function `replay_frames`: Run the pygame event loop that displays saved replay frames.
- Function `replay`: Load a recording file and replay it.
- Function `run_live_view`: Run an interactive pygame loop that steps, renders, and records an environment.
- Function `build_policy_step_actions`: Build one action per agent by querying each attached policy.
- Function `run_policy_live_view`: Run the live viewer with policy-driven stepping and `env.reset()`-based resets.
- Function `_run_render_session`: Build an env, optionally attach LLM policies, and run the shared live renderer.
- Function `Run_Render`: Public preset helper for rendered example CLIs.
- Function `_run_render_session_with_phases`: Run a rendered session with alternating discuss and act phases.

#### `renderers/runtime.py`
- Purpose: Preset module in the Word Play preset library.
- Function `configure_renderer`: Initialize renderer configuration, caches, and transient state.
- Function `apply_renderer_metrics`: Apply tile-size-derived layout metrics and rebuild dependent font state.
- Function `desktop_size`: Return the primary desktop size using display APIs meant for monitor geometry.
- Function `fitted_tile_size`: Choose a tile size that fits the display while keeping small scenes legible.
- Function `init_pygame_if_needed`: Create the pygame window and fonts the first time rendering is used.
- Function `ensure_screen_size`: Resize the pygame window only when the target dimensions change.
- Function `render_step`: Render one frame, pump events, and return `False` if the window was closed.

#### `renderers/wall_geometry.py`
- Purpose: Preset module in the Word Play preset library.
- Function `normalize_background_item`: Normalize background tile shorthands into a consistent dict shape.
- Function `world_bounds`: Compute visible world bounds from background tiles and entities.
- Function `screen_rect_for_tile`: Convert a world tile coordinate into the top-left screen pixel.
- Function `collect_wall_positions`: Extract the coordinates of all wall background tiles.
- Function `screen_position_for_entity`: Convert an entity position into its on-screen pixel location.
- Function `wall_neighbor_mask`: Report which neighboring wall tiles surround a wall cell.
- Function `wall_variant`: Classify a wall tile shape from its cardinal connections.
- Function `wall_connections`: Convert a neighbor mask into ordered connection direction names.
- Function `dirs_to_variant`: Format a set of directions into the wall sprite variant naming scheme.
- Function `adjacent_wall_variant_name`: Pick the sprite variant name implied by adjacent wall connections.

### Systems

#### `systems/__init__.py`
- Purpose: Systems - reusable game systems for Word Play.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `systems/action_compositions.py`
- Purpose: Action compositions — action chaining with per-step validation.
- Class `Step`: A single step in `Action_Comp`.
- Class `Required`: Required step; the chain fails if this step is invalid.
- Class `Optional`: Optional step; the chain skips this step if invalid.
- Class `Action_Comp`: Compose multiple actions into a single selectable action.

#### `systems/combat.py`
- Purpose: Combat system with attack behavior and target validation helpers.
- Class `Attack`: Action preset that damages a valid nearby target.

#### `systems/containers.py`
- Purpose: Container system for chests, infinite sources, regen pools, and single-item holders.
- Class `Open_Container`: Open a nearby container to reveal its contents.
- Class `Take_From_Infinite_Source`: Take an item from a `Regrowable_Item_Source` directly into inventory.
- Class `Container`: Chest-style container with hidden contents.
- Class `Regrowable_Item_Source`: Source that dispenses items through the inventory interface.
- Class `Regen_Pool`: Shared resource pool with depletion and regeneration dynamics.
- Class `Take_From_Regen_Pool`: Take an item from a `Regen_Pool` directly into inventory.
- Class `Clean_Pool`: Restore items to a `Regen_Pool`, usually as the inverse of taking from it.
- Class `Single_Item_Holder`: Container that can hold exactly one item.

#### `systems/cooldown.py`
- Purpose: Cooldown system for per-action cooldown tracking on entities.
- Class `Cooldown`: Tracks per-action cooldown ticks on an entity.
- Class `Action_On_Cooldown`: Validation rule that fails when the named action key is on cooldown.

#### `systems/crafter.py`
- Purpose: Crafter system for recipes, stations, and instant transforms.
- Class `Crafter_Recipe`: Recipe definition that maps input items to crafted outputs and timing rules.
- Class `Crafter`: Crafter that acts as a container where items are loaded, processed, and collected.
- Class `Load_Crafter`: Load an item into the crafter container.
- Class `Load_First_Into_Crafter`: Load the first compatible held item into a nearby crafter.
- Class `Collect_From_Crafter`: Collect the output from a crafter container.
- Class `Zap_Change`: Instantly transform a nearby zappable entity into a new form.
- Class `Zap_Change_Inventory`: Instantly transform a held inventory item into a different form.

#### `systems/currency.py`
- Purpose: Currency system where `Money` stores amount and the renderer handles display.
- Class `Currency_Amount_Arg`: Argument for selecting a currency amount.
- Class `Money`: Money component that stores amount and can be rendered as cash.
- Class `Has_Money`: Validation that an entity has a `Money` component.
- Class `Has_Currency`: Validation that an entity's money is positive.

#### `systems/delivery.py`
- Purpose: Delivery helpers for item validation, reward computation, and delivery side effects.
- Class `Front_Order_Match`: Item validator that checks whether the item matches the front of an order queue.
- Class `Named_Item_Reward`: Reward function that pays by item name with a default fallback.
- Class `Record_Delivery`: Side-effect callback that updates score, order queue, and event log on delivery.
- Class `Deliver_Item`: Deliver an inventory item to a tagged target for reward.

#### `systems/destructible.py`
- Purpose: Destructible system for entities that transform when their HP reaches zero.
- Class `Destructible`: Entity that transforms into another form when its HP hits zero.

#### `systems/do_nothing.py`
- Purpose: No-op action preset for skipping an agent's turn.
- Class `Do_Nothing`: Action preset that intentionally skips the actor turn.

#### `systems/freezable.py`
- Purpose: Freezable system for temporarily holding an entity in place.
- Class `Freezable`: Entity that can be frozen in place for a duration.
- Class `Freeze`: Freeze a nearby freezable entity for a duration.

#### `systems/health.py`
- Purpose: Health system for HP tracking, damage, and death.
- Class `Health`: Health component with max and current health tracking.

#### `systems/inventory.py`
- Purpose: Inventory system with base storage, item arguments, and inventory actions.
- Class `Target_Not_In_Inventory`: Validation ensuring a target entity is not stored in any agent inventory.
- Class `Inventory_Item_Index_Arg`: Argument for selecting an item from inventory by index.
- Class `Inventory_Items_Arg`: Argument for selecting multiple inventory items by comma-separated indices.
- Function `_set_item_visibility`: Set item visibility through its `Renderable` component.
- Function `materialize_item`: Create an item from a spec, entity, or factory callable.
- Class `Inventory`: Generic storage base class for inventories, containers, and sources.
- Class `Pick_Up_Item`: Pick up an item from the environment into inventory.
- Class `Put_In_Container`: Put an inventory item into a container.
- Class `Drop_Item`: Drop an inventory item onto the ground at the actor position.

#### `systems/ownership.py`
- Purpose: Ownership system for claiming and transferring ownership.
- Class `Owner`: Track who owns an entity.
- Class `Ownable`: Marker component for claimable entities, usually paired with `Owner`.
- Class `Target_Is_Unowned`: Validate that a target currently has no owner.
- Class `Claim`: Claim ownership of an unowned entity.
- Class `Give_Ownership`: Give an owned entity to another agent.

#### `systems/preferences.py`
- Purpose: Preference system for tag-based reward preferences on agents.
- Class `Preference`: Map target entity tags to reward amounts.

#### `systems/regrowable.py`
- Purpose: Regrowable system for consumable entities that reappear on a timer.
- Class `Regrowable`: Entity that can be consumed and regrows after a cooldown.
- Class `Consume_Regrowable`: Consume a nearby regrowable entity.
- Class `Harvest_Regrowable`: Harvest a nearby regrowable entity into inventory.

#### `systems/reward.py`
- Purpose: Reward system for target-side reward definitions and reward application.
- Class `Rewardable`: Define the reward an actor receives for interacting with an entity.
- Function `award_reward`: Add reward to the actor entry in `env.last_step_rewards`.

#### `systems/team_marker.py`
- Purpose: Team marker system for team identification and ally or enemy validation.
- Class `Team`: Mark an entity as belonging to a team.
- Class `Target_Is_Enemy`: Validation that a target belongs to a different team.
- Class `Target_Is_Ally`: Validation that a target belongs to the same team.

#### `systems/zap.py`
- Purpose: Zap system for instant transforms, player attacks, and inventory consumes.
- Class `ZapMarking`: Graduated-sanctions marker that tracks zap-hit level on a player.
- Class `Zap_Player`: Zap a nearby player with graduated sanctions.
- Class `Zap_Change`: Instantly transform a nearby entity into a new form.
- Class `Zap_Change_Inventory`: Instantly transform a held inventory item into a different form.

### Systems / Communication

#### `systems/communication/__init__.py`
- Purpose: Communication preset namespace combining chat-room and trade communication building blocks.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `systems/communication/core.py`
- Purpose: Base communication-policy module used by the communication presets.
- Class `Communication_Policy`: Base interface for policies that generate communication acts or messages.

### Systems / Communication / Chat Room Action Communication

#### `systems/communication/chat_room_action_communication/__init__.py`
- Purpose: Chat-room communication namespace for public and private conversation actions and policies.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `systems/communication/chat_room_action_communication/core.py`
- Purpose: Core chat-room communication actions, partner selection helpers, and validations.
- Function `nearby_conversation_partners`: List nearby entities that are eligible conversation partners.
- Function `sim_simple_conversation`: Run a lightweight conversation exchange inside one environment step.
- Class `A_Conversation_Partner_Is_Nearby`: Validation rule requiring at least one nearby communication partner.
- Class `Start_Public_Conversation`: Action that starts a public nearby conversation visible to others.
- Function `partner_idx_list_is_valid`: Validate a selected list of conversation-partner indices.
- Class `Nearby_Partner_Indicies`: Argument preset for selecting nearby conversation partners by index.
- Class `Start_Private_Conversation`: Action that starts a private conversation with chosen nearby partners.

### Systems / Communication / Chat Room Action Communication / Presets

#### `systems/communication/chat_room_action_communication/presets/policies.py`
- Purpose: Concrete communication-policy presets for simple chat-room interactions.
- Class `Human_Communication_Policy`: Communication policy that asks a real person what to say.
- Class `TalkingCow`: Toy communication policy preset used for simple scripted chat behavior.

### Systems / Communication / Trade Communication

#### `systems/communication/trade_communication/__init__.py`
- Purpose: Trade communication namespace for negotiation policies, state, and actions.
- Notes: Export-only package file; use it as an import surface rather than as a behavior implementation module.

#### `systems/communication/trade_communication/core.py`
- Purpose: Trading-policy core module for negotiation behavior and negotiation simulation.
- Class `Trading_Policy`: Interface for trade negotiation behavior.
- Function `sim_trade_negotiation`: Run a bilateral trade negotiation within a single step.

#### `systems/communication/trade_communication/trade_actions.py`
- Purpose: Trade actions, trade session state, and validations.
- Class `Trade_Offer`: Structured offer object describing items, currency, and acceptance state in a trade.
- Class `Trade_Session`: Trade session attached to both participants during trade.
- Class `In_Active_Trade`: Validation rule requiring the actor to already be inside a live trade session.
- Class `Can_Start_Trade`: Validation rule checking whether a target is eligible to begin trading.
- Class `Start_Trade`: Start a trade with a nearby entity.

### Systems / Communication / Trade Communication / Presets

#### `systems/communication/trade_communication/presets/policies.py`
- Purpose: Concrete `Trading_Policy` presets.
- Class `Simple_Trading_Policy`: Combined action, communication, and trading policy backed by any `Model`.
