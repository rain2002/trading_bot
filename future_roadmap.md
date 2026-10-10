# Quantitative Trading Bot - Future Roadmap

## Phase 3: The "Final Boss" Level (Genetic Programming & Machine Learning)

*This file serves as a permanent reminder to eventually migrate away from parameter-optimization and into pure algorithmic discovery.*

### The Goal
Instead of manually hardcoding indicators (Moving Averages, RSI), the bot will use **Genetic Programming** and **Symbolic Regression** to invent entirely new, hidden mathematical formulas by breeding successful algorithms together and mutating them.

### Hardware Requirements (The Bottleneck)
This cannot be run on GitHub Actions. It requires a dedicated server.
1. **Option A (Cloud VPS - AWS/RunPod):** ~$50 to $150/month for an instance with a dedicated GPU and 32GB+ RAM. 
2. **Option B (Home Quant Server):** ~$800 to $1,500 one-time cost to build a custom desktop (e.g., AMD Ryzen 9, 64GB RAM, RTX 4060). *Highly recommended for long-term quantitative research, as it eliminates monthly cloud fees.*

### The Overfitting Trap
When we implement this, we must build rigorous "Out-of-Sample" and "Monte Carlo" stress tests to ensure the machine isn't just memorizing historical noise. 
