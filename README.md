<div align="center">
  <img src="https://github.com/user-attachments/assets/a3b2a647-dbc3-41a3-add1-2d713678aa96" alt="System V0.4" width="1000" style="border-radius: 20px; margin-bottom: 20px; box-shadow: 0 20px 20px rgba(0,0,0,0.4);">
  
```mermaid
graph LR
    subgraph World [Simulation Environment]
        E[Events]
    end

    subgraph Brain [LFM2.5 Model]
        N[Neural Engine]
    end

    subgraph Actors [Agents]
        A1(Agent 1)
        A2(Agent 2)
        A3(Agent 3)
    end

    E -->|Data| N
    N -->|Commands| A1 & A2 & A3
    A1 & A2 & A3 -->|Feedback| E
```
