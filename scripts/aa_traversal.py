def apply_traversal_steps(*args, **kwargs):
    """
    Compatibility entrypoint expected by scene_build.py.

    This wrapper forwards to the module's real implementation, which may have a
    different name (older/newer refactor), e.g. apply_steps(), run_traversal(), main(), etc.
    """
    # Try a few likely function names that might already exist in this module.
    for name in (
        "apply_steps",
        "run_traversal",
        "run_traversal_steps",
        "apply_traversal",
        "main",
    ):
        fn = globals().get(name)
        if callable(fn) and fn is not apply_traversal_steps:
            return fn(*args, **kwargs)

    raise ImportError(
        "apply_traversal_steps was called, but aa_traversal.py does not define a traversal "
        "implementation (apply_steps/run_traversal/main). Add one, or rename the import."
    )

{
  "nodeMap": {
    "1": "Patient",
    "2": "Encounter",
    "3": "Specimen",
    "4": "ObservationA",
    "5": "PractitionerLab",
    "6": "ObservationB",
    "7": "PractitionerOrder"
  },
  "steps": [
    { "step": 1, "activateNodes": ["1"] },
    { "step": 2, "activateNodes": ["2"] },
    { "step": 3, "activateNodes": ["4","6"] },
    { "step": 4, "activateNodes": ["5","7"] }
  ]
}
