<div align="center">

  <!-- ЛОГОТИП -->
  <img src="https://github.com/user-attachments/assets/a3b2a647-dbc3-41a3-add1-2d713678aa96" alt="System V0.4" width="500" style="border-radius: 20px; margin-bottom: 20px; box-shadow: 0 20px 20px rgba(0,0,0,0.4);">
  

  <!-- БЕЙДЖИ -->
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.9+](https://img.shields.io/badge/python-3.12.7-blue.svg)](https://www.python.org/downloads/)
  [![LLM](https://img.shields.io/badge/Model-LFM2.5--1.2B-green.svg)]()



 ### 🏗️ Architecture
 <p><b> Multi-agent simulation driven by a small-form neural network</b></p>
The system is based on the interaction of three independent agents and a central neural network.

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

