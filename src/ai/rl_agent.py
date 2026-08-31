# src/ai/rl_agent.py
"""Reinforcement Learning Agent untuk Claw Royale Bot"""

import json
import logging
import random
import math
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import datetime

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    state: Tuple
    action: str
    reward: float
    next_state: Tuple
    done: bool


class QLearningAgent:
    LEARNING_RATE = 0.1
    DISCOUNT_FACTOR = 0.95
    EPSILON_START = 1.0
    EPSILON_END = 0.05
    EPSILON_DECAY = 0.995
    MEMORY_SIZE = 1000
    BATCH_SIZE = 32
    
    HP_BINS = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
    ENEMY_BINS = [0, 1, 2, 3, 5, 10]
    ITEM_BINS = [0, 1, 2, 3, 5, 10]
    ALERT_BINS = [0, 3, 7, 10]
    DANGER_BINS = [0, 0.3, 0.6, 1.0]
    
    ACTIONS = ["attack", "pickup", "move", "explore", "interact", "use", "wait"]
    
    def __init__(self, storage_path: str = "rl_knowledge.json"):
        self.storage_path = storage_path
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.memory = []
        self.epsilon = self.EPSILON_START
        self.episode = 0
        self.total_reward = 0
        self.steps = 0
        
        self.last_state = None
        self.last_action = None
        self.last_reward = 0
        
        self.stats = {
            "episodes": 0,
            "total_reward": 0,
            "avg_reward": 0,
            "exploration_actions": 0,
            "exploitation_actions": 0,
            "learning_updates": 0
        }
        
        self._load()
    
    def _load(self):
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                self.q_table = defaultdict(lambda: defaultdict(float))
                for state_str, actions in data.get("q_table", {}).items():
                    for action, value in actions.items():
                        self.q_table[state_str][action] = value
                self.epsilon = data.get("epsilon", self.EPSILON_START)
                self.episode = data.get("episode", 0)
                self.stats = data.get("stats", self.stats)
                logger.info(f"🧠 Loaded RL knowledge: {len(self.q_table)} states")
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("🧠 No existing RL knowledge, starting fresh")
    
    def save(self):
        try:
            q_table_dict = {}
            for state, actions in self.q_table.items():
                q_table_dict[state] = dict(actions)
            
            data = {
                "q_table": q_table_dict,
                "epsilon": self.epsilon,
                "episode": self.episode,
                "stats": self.stats,
                "last_updated": datetime.datetime.now().isoformat()
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"💾 RL knowledge saved ({len(self.q_table)} states)")
        except Exception as e:
            logger.error(f"Failed to save RL knowledge: {e}")
    
    def _discretize_state(self, state: Dict) -> Tuple:
        hp = state.get("hp_ratio", 0)
        enemy_count = min(state.get("enemy_count", 0), 5)
        items_nearby = min(state.get("items_nearby", 0), 5)
        in_cave = 1 if state.get("in_cave", False) else 0
        alert = state.get("alert_level", 0)
        danger = state.get("danger_level", 0)
        
        hp_bin = self._get_bin(hp, self.HP_BINS)
        enemy_bin = self._get_bin(enemy_count, self.ENEMY_BINS)
        item_bin = self._get_bin(items_nearby, self.ITEM_BINS)
        alert_bin = self._get_bin(alert, self.ALERT_BINS)
        danger_bin = self._get_bin(danger, self.DANGER_BINS)
        
        return (hp_bin, enemy_bin, item_bin, in_cave, alert_bin, danger_bin)
    
    def _get_bin(self, value: float, bins: List[float]) -> int:
        for i, threshold in enumerate(bins):
            if value < threshold:
                return i
        return len(bins) - 1
    
    def get_state_features(self, game_state) -> Dict:
        hp_ratio = game_state.hp_ratio()
        enemies = game_state.get_enemies()
        items = game_state.get_valid_items()
        alert = game_state.alert_gauge
        region = game_state.get_region()
        
        danger = 0
        if enemies:
            closest = min(enemies, key=lambda e: game_state._calculate_distance(game_state.get_self(), e))
            distance = game_state._calculate_distance(game_state.get_self(), closest)
            danger = min(1, 1 / max(distance, 1) * 0.5 + len(enemies) * 0.1)
        
        return {
            "hp_ratio": hp_ratio,
            "enemy_count": len(enemies),
            "items_nearby": len(items),
            "in_cave": game_state.in_cave,
            "alert_level": alert,
            "danger_level": danger
        }
    
    def get_reward(self, game_state, action: str, success: bool) -> float:
        reward = 0.0
        
        hp_ratio = game_state.hp_ratio()
        if hp_ratio > 0.8:
            reward += 0.3
        elif hp_ratio > 0.5:
            reward += 0.1
        elif hp_ratio < 0.2:
            reward -= 0.5
        
        if action == "pickup" and success:
            reward += 0.5
            reward += 0.2
        elif action == "attack" and success:
            reward += 1.0
        elif action == "explore" and success:
            reward += 0.8
        elif action == "use" and success:
            reward += 0.3
        elif action == "move" and success:
            reward += 0.1
        
        if action == "wait":
            reward -= 0.05
        
        if not game_state.is_alive:
            reward -= 2.0
        
        return reward
    
    def choose_action(self, state: Dict, available_actions: List[str]) -> Tuple[str, bool]:
        discretized = self._discretize_state(state)
        state_key = str(discretized)
        
        if random.random() < self.epsilon:
            action = random.choice(available_actions)
            self.stats["exploration_actions"] += 1
            return action, True
        
        self.stats["exploitation_actions"] += 1
        
        q_values = {a: self.q_table[state_key].get(a, 0.0) for a in available_actions}
        
        if q_values:
            best_action = max(q_values, key=q_values.get)
            return best_action, False
        
        return random.choice(available_actions), False
    
    def learn(self, state: Dict, action: str, reward: float, next_state: Dict, done: bool):
        current_state = self._discretize_state(state)
        next_state_disc = self._discretize_state(next_state)
        
        current_key = str(current_state)
        next_key = str(next_state_disc)
        
        current_q = self.q_table[current_key].get(action, 0.0)
        
        next_actions = self.ACTIONS
        next_q_values = [self.q_table[next_key].get(a, 0.0) for a in next_actions]
        max_next_q = max(next_q_values) if next_q_values else 0
        
        new_q = current_q + self.LEARNING_RATE * (
            reward + self.DISCOUNT_FACTOR * max_next_q * (not done) - current_q
        )
        
        self.q_table[current_key][action] = new_q
        
        self.memory.append(Experience(
            state=current_state,
            action=action,
            reward=reward,
            next_state=next_state_disc,
            done=done
        ))
        
        if len(self.memory) > self.MEMORY_SIZE:
            self.memory = self.memory[-self.MEMORY_SIZE:]
        
        self.stats["learning_updates"] += 1
        self.total_reward += reward
        
        self.epsilon = max(self.EPSILON_END, self.epsilon * self.EPSILON_DECAY)
        
        if self.stats["learning_updates"] % 50 == 0:
            self.save()
    
    def get_q_value(self, state: Dict, action: str) -> float:
        discretized = self._discretize_state(state)
        state_key = str(discretized)
        return self.q_table[state_key].get(action, 0.0)
    
    def get_best_action(self, state: Dict, available_actions: List[str]) -> str:
        discretized = self._discretize_state(state)
        state_key = str(discretized)
        
        q_values = {a: self.q_table[state_key].get(a, 0.0) for a in available_actions}
        if q_values:
            return max(q_values, key=q_values.get)
        return random.choice(available_actions)
    
    def get_action_probabilities(self, state: Dict) -> Dict[str, float]:
        discretized = self._discretize_state(state)
        state_key = str(discretized)
        
        q_values = {a: self.q_table[state_key].get(a, 0.0) for a in self.ACTIONS}
        total = sum(q_values.values())
        
        if total > 0:
            return {a: v/total for a, v in q_values.items()}
        return {a: 1.0/len(self.ACTIONS) for a in self.ACTIONS}
    
    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "epsilon": round(self.epsilon, 3),
            "q_table_size": len(self.q_table),
            "memory_size": len(self.memory),
            "total_reward": round(self.total_reward, 2)
        }
    
    def reset_episode(self):
        self.episode += 1
        self.total_reward = 0
        self.steps = 0
        self.stats["episodes"] += 1