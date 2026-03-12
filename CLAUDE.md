# CLAUDE.md

## Engineering Principles

This repository follows **testable, modular, and decoupled
architecture** practices.

While classical **Dependency Injection (DI)** is preferred, ML/LLM
pipelines sometimes require pragmatic adaptations. The goal is to
maintain **high testability, reproducibility, and maintainability**
across ML, LLM, and infrastructure code.

Core principles:

-   Prefer **Dependency Injection** over hard-coded dependencies
-   Write **testable components**
-   Keep **business logic independent from infrastructure**
-   Build **loosely coupled pipelines**
-   Ensure **reproducibility of ML workflows**
-   Favor **simple, readable code over clever abstractions**

------------------------------------------------------------------------

# Architecture Guidelines

## Dependency Injection First

Whenever possible:

-   Pass dependencies via **constructor or function arguments**
-   Avoid instantiating services inside business logic
-   Use **interfaces or abstract classes** for replaceable components

### Good

``` python
class EmbeddingService:
    def embed(self, text: str) -> list[float]:
        ...


class Retriever:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
```

### Avoid

``` python
class Retriever:
    def __init__(self):
        self.embedding_service = OpenAIEmbedding()
```

Benefits:

-   Easier testing
-   Better mocking
-   Easier model/provider swapping

------------------------------------------------------------------------

# ML / LLM Design Philosophy

ML systems should be treated as **data pipelines**, not monolithic
applications.

Priorities:

-   Modular stages
-   Reproducibility
-   Experiment traceability
-   Explicit inputs and outputs

Typical workflow:

    data ingestion
        ↓
    data preprocessing
        ↓
    feature engineering / embedding
        ↓
    model training or LLM orchestration
        ↓
    evaluation
        ↓
    deployment

Each stage must:

-   accept **explicit inputs**
-   produce **explicit outputs**
-   avoid hidden side effects

------------------------------------------------------------------------

# Pipeline Design (MLOps / LLMOps)

Pipelines must be **decoupled and composable**.

Rules:

1.  Each pipeline stage should be a **pure function or isolated
    service**
2.  Avoid reliance on **global state**
3.  Pass artifacts explicitly between stages
4.  Stages must be **individually runnable**

Example structure:

    pipelines/
        ingestion/
        preprocessing/
        embedding/
        training/
        evaluation/
        inference/

------------------------------------------------------------------------

# LLM System Design

Separate responsibilities clearly.

    prompt construction
    model inference
    post-processing
    evaluation

Recommended structure:

    llm/
        prompts/
        providers/
        chains/
        evaluators/

This enables:

-   swapping LLM providers easily
-   testing prompts independently
-   offline evaluation pipelines

------------------------------------------------------------------------

# DevOps / MLOps Practices

## Reproducibility

Experiments must be reproducible.

Track:

-   model versions
-   dataset versions
-   prompt versions
-   hyperparameters
-   evaluation results

Prefer:

-   configuration files
-   experiment tracking tools
-   deterministic pipelines when possible

------------------------------------------------------------------------

## Configuration Management

Avoid hardcoded values.

Use configuration files:

    configs/
        model.yaml
        pipeline.yaml
        inference.yaml

Configurations should be **injected into services**, not globally
imported.

------------------------------------------------------------------------

# Testing Philosophy

Testability is a **first-class requirement**.

## Unit Tests

Test individual components:

-   prompt builders
-   retrievers
-   feature extractors
-   model wrappers

## Integration Tests

Test interactions between pipeline stages.

## Evaluation Tests

Automated evaluation for:

-   LLM quality
-   regression detection
-   pipeline correctness

------------------------------------------------------------------------

# Observability

Production systems should include:

-   structured logging
-   metrics
-   tracing

Important metrics:

-   model latency
-   token usage
-   error rates
-   evaluation scores

------------------------------------------------------------------------

# Code Organization

Preferred structure:

    src/
        core/            # domain logic
        services/        # reusable services
        pipelines/       # ML/LLM pipelines
        infrastructure/  # database, API, cloud integrations
        configs/
        utils/

    tests/

Rules:

-   `core` must **not depend on infrastructure**
-   `services` should be **mockable**
-   `pipelines` orchestrate components only

------------------------------------------------------------------------

# Anti-Patterns to Avoid

Avoid:

-   hidden global states
-   tightly coupled pipelines
-   model calls embedded inside business logic
-   mixing infrastructure with ML logic
-   monolithic scripts that cannot be tested

------------------------------------------------------------------------

# Guiding Principle

> Build ML systems like software systems.

Prioritize:

-   clarity
-   modularity
-   testability
-   reproducibility
