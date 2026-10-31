# 01 — MCP vs Code Mode

> **Status:** Not started — scaffolding only
> **Experiment version:** 0.1.0
> **Last updated:** 2026-10-31

## 1. Overview

This experiment compares Model Context Protocol (MCP) tool calling with programmatic tool orchestration ("Code Mode": the model writes code that calls tools via an API inside a sandbox) for the same workflow.

## 2. Research Question

For an equivalent multi-step tool workflow, how do MCP-based tool calling and Code Mode differ in context overhead, token consumption, latency, reliability and security posture?

## 3. Why This Matters

As the number of tools grows, so does the context a model must carry. The choice of approach affects cost, latency and attack surface.

## 4. Hypothesis

All hypotheses below are unverified and will be tested.

- **H1 (unverified):** Code Mode uses fewer tokens on multi-step workflows because intermediate results need not pass through the model context.
- **H2 (unverified):** Code Mode adds latency and complexity from sandbox startup.
- **H3 (unverified):** MCP offers simpler tool discovery and a more standardised auth model.

## 5. Objectives

Compare the two approaches across these dimensions:

1. Architecture
2. Tool discovery
3. Tool execution
4. Authentication
5. Authorization
6. Context overhead
7. Token consumption
8. Latency
9. Reliability
10. Security
11. Scalability

## 6. Scope

### In scope

A simulated banking account information workflow using synthetic data only, with five capabilities:

1. Retrieve customer information
2. Retrieve customer account details
3. Retrieve account balances
4. Retrieve recent transactions
5. Generate a customer account summary

Both approaches must eventually run equivalent workflows under equal security assumptions:

- Authentication
- Authorization
- Tool access restrictions
- Input validation
- Execution timeouts
- Error handling
- Audit logging

For Code Mode, generated code runs only in a sandbox with filesystem restrictions, network restrictions, resource limits, execution timeouts, restricted credentials and explicit tool allowlists. Authorization is enforced by the banking simulation, never by the LLM.

### Out of scope

- Real banking data or systems
- Production deployment

## 7. Architecture

See [architecture/overview.md](architecture/overview.md) for the planned (draft) architecture.

## 8. Implementation Approaches

To be decided in the design phase. Open questions:

- Which MCP SDK?
- Which sandbox technology?
- Which model?

## 9. Technology Stack

To be decided in the design phase. No choices have been made.

## 10. Experimental Methodology

Detailed methodology to be defined. Iterations, warm-up and concurrency will be decided during methodology design and stated here.

## 11. Evaluation Metrics

Planned metrics (estimated values will be labelled as estimated):

- Average, p50 and p95 latency
- Success and failure rate
- Input, output and total tokens
- Estimated cost
- Context overhead

See [benchmarking standards](../../docs/standards/benchmarking-standards.md).

## 12. Results

> Results pending. Do not fill in until benchmarks have been run.

## 13. Analysis

> Results pending. Do not fill in until benchmarks have been run.

## 14. Limitations

To be documented once the methodology is defined.

## 15. Conclusion

> Results pending. Do not fill in until benchmarks have been run.

## 16. How to Run

Not yet implemented.

## 17. References

- Model Context Protocol — https://modelcontextprotocol.io
- Cloudflare, "Code Mode: the better way to use MCP" — https://blog.cloudflare.com/code-mode/
- Anthropic, "Code execution with MCP" — https://www.anthropic.com/engineering/code-execution-with-mcp
