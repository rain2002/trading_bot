"""
Phase 4: The Final Boss
Module: Symbolic Expression Trees
Represents trading rules as mathematical syntax trees that can be
evaluated, mutated, and bred via Genetic Programming.
"""

from typing import Any, List
import pandas as pd
import numpy as np
import random


class ExpressionNode:
    """Base class for AST nodes representing strategy rules."""
    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def to_formula(self) -> str:
        raise NotImplementedError

    def copy(self) -> "ExpressionNode":
        raise NotImplementedError


class TerminalNode(ExpressionNode):
    """Leaf node: raw price series or statistical indicator."""
    def __init__(self, name: str, param: int = 14):
        self.name = name
        self.param = param

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        if self.name == "close":
            return close
        elif self.name == "volume":
            return df.get("volume", pd.Series(1.0, index=df.index))
        elif self.name == "sma":
            return close.rolling(window=self.param).mean()
        elif self.name == "ema":
            return close.ewm(span=self.param, adjust=False).mean()
        elif self.name == "std":
            return close.rolling(window=self.param).std()
        elif self.name == "rsi":
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(self.param).mean()
            loss = (-delta.clip(upper=0)).rolling(self.param).mean()
            rs = gain / loss.replace(0, np.nan)
            return (100 - (100 / (1 + rs))).fillna(50)
        return close

    def to_formula(self) -> str:
        if self.name in ["close", "volume"]:
            return self.name.upper()
        return f"{self.name.upper()}({self.param})"

    def copy(self) -> "TerminalNode":
        return TerminalNode(self.name, self.param)


class ConstantNode(ExpressionNode):
    """Leaf node representing a numeric constant."""
    def __init__(self, value: float):
        self.value = value

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=df.index)

    def to_formula(self) -> str:
        return f"{self.value:.2f}"

    def copy(self) -> "ConstantNode":
        return ConstantNode(self.value)


class BinaryOpNode(ExpressionNode):
    """Operator node: compares or combines two sub-expressions."""
    def __init__(self, op: str, left: ExpressionNode, right: ExpressionNode):
        self.op = op  # '>', '<', '+', '-', '*', 'AND', 'OR'
        self.left = left
        self.right = right

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        l_val = self.left.evaluate(df)
        r_val = self.right.evaluate(df)

        if self.op == ">":
            return (l_val > r_val).astype(float)
        elif self.op == "<":
            return (l_val < r_val).astype(float)
        elif self.op == "+":
            return l_val + r_val
        elif self.op == "-":
            return l_val - r_val
        elif self.op == "*":
            return l_val * r_val
        elif self.op == "AND":
            return ((l_val > 0) & (r_val > 0)).astype(float)
        elif self.op == "OR":
            return ((l_val > 0) | (r_val > 0)).astype(float)
        return pd.Series(0.0, index=df.index)

    def to_formula(self) -> str:
        return f"({self.left.to_formula()} {self.op} {self.right.to_formula()})"

    def copy(self) -> "BinaryOpNode":
        return BinaryOpNode(self.op, self.left.copy(), self.right.copy())
