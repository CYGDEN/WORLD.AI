<div align="center">
  <img src="https://github.com/user-attachments/assets/a3b2a647-dbc3-41a3-add1-2d713678aa96" alt="System V0.4" width="1000" style="border-radius: 20px; margin-bottom: 20px; box-shadow: 0 20px 20px rgba(0,0,0,0.4);">
  
```mermaid
graph LR
    subgraph World [ ]
        E[INSTRUCTION]
    end

    subgraph Brain [ ]
        N[MODEL]
    end

    subgraph Actors [ ]
        A1(1)
        A2(2)
        A3(3)
    end

    E -->| | N
    N -->|ACTION| A1 & A2 & A3
    A1 & A2 & A3 -->|LOG| E
```
