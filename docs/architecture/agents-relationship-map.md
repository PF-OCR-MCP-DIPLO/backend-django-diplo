# Agents Relationship Map

```mermaid
graph TB
    subgraph L1[Level 1: Deterministic Pipeline]
        OA[OCR Agent]
        EA[Extraction Agent]
        VPA[ValidationPersistenceAgent]
        OA --> EA --> VPA
    end

    subgraph L2[Level 2: Intelligent Agent Layer]
        CA[Cleaning Agent]
        VA[Validation Agent]
        RA[Retry Agent]
        AA[Aggregation Agent]
    end

    ORCH[ProcessingSupervisorAgent\n(Orchestrator)]

    ORCH --> OA
    ORCH --> CA
    ORCH --> EA
    ORCH --> VA
    ORCH --> RA
    ORCH --> AA
    ORCH --> VPA

    OA --> CA
    CA --> EA
    EA --> VA
    VA --> RA
    RA --> ORCH
    AA --> VPA
```
