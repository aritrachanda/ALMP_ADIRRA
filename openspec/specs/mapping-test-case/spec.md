## ADDED Requirements

### Requirement: Guarantee mapping test script
A standalone Python script SHALL exist at `tests/test_guarantee_mapping.py` that runs the mapping agent for `banking → CRDM` scoped to a single target table (`CRDM.input.Guarantee`) and saves the result for manual review.

#### Scenario: Run test script
- **WHEN** the user executes `python tests/test_guarantee_mapping.py`
- **THEN** the script SHALL load the banking source catalog, CRDM target catalog, and banking annotations, call `map_source_to_target` with `target_tables={"CRDM.input.Guarantee"}`, save the mapping YAML to `tests/golden/banking_to_crdm_guarantee.yaml`, and print a summary of mapped/derived/unmapped column counts with average confidence

#### Scenario: Run without annotations for baseline comparison
- **WHEN** the user executes `python tests/test_guarantee_mapping.py --no-annotations`
- **THEN** the script SHALL run the same mapping without passing annotations, save to `tests/golden/banking_to_crdm_guarantee_baseline.yaml`, and print the same summary

### Requirement: Test output is reviewable
The saved YAML output SHALL use the standard mapping format (version 2) so it can be loaded in the Mapping UI page or diffed with standard tools.

#### Scenario: View test output in Mapping page
- **WHEN** the user copies the test output YAML to `mappings/`
- **THEN** the Mapping UI page SHALL be able to load and display it like any other mapping
