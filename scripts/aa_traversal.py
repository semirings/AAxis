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
