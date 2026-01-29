import asyncio
import aiohttp
import logging
import json
import random
import math
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import pygame

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Config:
    LLM_URL = "http://127.0.0.1:8080/completion"
    LLM_TIMEOUT = 60
    SCREEN_WIDTH = 1400
    SCREEN_HEIGHT = 800
    FPS = 60
    AI_THINK_INTERVAL = 90
    MOVE_SPEED = 5.0
    NEED_DECAY = 0.006
    CRITICAL = 2.5
    LOW = 4.0
    MAX_HEALTH = 100.0


class Theme:
    BG = (15, 15, 18)
    CARD = (26, 26, 30)
    BORDER = (50, 50, 55)
    TEXT = (255, 255, 255)
    TEXT_DIM = (130, 130, 135)
    TEXT_MUTED = (90, 90, 95)
    BLUE = (10, 132, 255)
    GREEN = (48, 209, 88)
    ORANGE = (255, 159, 10)
    RED = (255, 69, 58)
    ZONE_HOME = (40, 45, 75)
    ZONE_WORK = (65, 50, 40)
    ZONE_CAFE = (75, 55, 45)
    ZONE_PARK = (35, 65, 45)
    ZONE_ROAD = (30, 30, 35)


class ZoneType(Enum):
    HOME = "home"
    WORK = "work"
    CAFE = "cafe"
    PARK = "park"
    ROAD = "road"


class Goal(Enum):
    IDLE = "idle"
    GO_HOME = "go_home"
    GO_WORK = "go_work"
    GO_CAFE = "go_cafe"
    GO_PARK = "go_park"


ZONE_FOR_GOAL = {
    Goal.GO_HOME: ZoneType.HOME,
    Goal.GO_WORK: ZoneType.WORK,
    Goal.GO_CAFE: ZoneType.CAFE,
    Goal.GO_PARK: ZoneType.PARK,
}

ZONE_EFFECTS = {
    ZoneType.HOME: {"energy": 0.12},
    ZoneType.WORK: {"work": 0.15},
    ZoneType.CAFE: {"hunger": 0.18, "social": 0.08},
    ZoneType.PARK: {"energy": 0.06, "social": 0.10},
}

NEED_FIX = {
    "hunger": "go_cafe",
    "energy": "go_home",
    "social": "go_park",
    "work": "go_work",
}

NEED_NAMES = {"hunger": "Голод", "energy": "Энергия", "social": "Общение", "work": "Работа"}


@dataclass
class Zone:
    name: str
    type: ZoneType
    rect: pygame.Rect
    color: Tuple[int, int, int]

    @property
    def center(self) -> Tuple[int, int]:
        return self.rect.center


class PathGraph:
    def __init__(self, zones: List[Zone]):
        self.pos: Dict[str, Tuple[int, int]] = {}
        self.adj: Dict[str, List[str]] = {}

        for z in zones:
            self.pos[z.name] = z.center
            self.adj[z.name] = []

        names = list(self.pos.keys())
        for a in names:
            dists = sorted(
                [(math.hypot(self.pos[a][0] - self.pos[b][0], self.pos[a][1] - self.pos[b][1]), b)
                 for b in names if a != b]
            )
            for _, nb in dists[:4]:
                if nb not in self.adj[a]:
                    self.adj[a].append(nb)
                if a not in self.adj[nb]:
                    self.adj[nb].append(a)

    def find(self, start: str, end: str) -> List[Tuple[int, int]]:
        if start == end:
            return [self.pos[start]]

        queue = deque([[start]])
        seen = {start}

        while queue:
            path = queue.popleft()
            if path[-1] == end:
                return [self.pos[n] for n in path]
            for nb in self.adj.get(path[-1], []):
                if nb not in seen:
                    seen.add(nb)
                    queue.append(path + [nb])

        return [self.pos[start], self.pos[end]]


@dataclass
class Agent:
    id: str
    name: str
    color: Tuple[int, int, int]
    home: Zone
    graph: PathGraph
    zones: List[Zone] = field(default_factory=list)

    pos: List[float] = field(default_factory=list)
    zone: Optional[Zone] = None
    health: float = 100.0
    alive: bool = True
    death_reason: str = ""
    thought: str = "..."

    needs: Dict[str, float] = field(default_factory=dict)
    goal: Goal = Goal.IDLE
    target: Optional[Zone] = None
    path: List[Tuple[int, int]] = field(default_factory=list)
    path_i: int = 0
    wait: int = 0

    def __post_init__(self):
        self.pos = list(self.home.center)
        self.zone = self.home
        self.needs = {
            "hunger": random.uniform(5.0, 7.0),
            "energy": random.uniform(5.5, 7.5),
            "social": random.uniform(4.5, 7.0),
            "work": random.uniform(4.0, 6.0),
        }

    def assign(self, goal: Goal, target: Optional[Zone]):
        if not self.alive:
            return

        if goal == Goal.IDLE:
            self.goal = Goal.IDLE
            self.target = None
            self.path = []
            return

        if self.zone and target and self.zone.name == target.name:
            return

        if self.goal == goal and self.target == target and self.path:
            return

        self.goal = goal
        self.target = target
        self.wait = 0

        if target:
            start = self.zone.name if self.zone else self.home.name
            self.path = self.graph.find(start, target.name)
            self.path_i = 0
            logger.info(f"{self.name}: {goal.value} -> {target.name}")

    def tick(self):
        if not self.alive:
            return

        self._decay()
        self._zone_effect()
        self._health_check()
        self._move()
        self._detect_zone()

        if self.goal == Goal.IDLE:
            self.wait += 1

    def _decay(self):
        for k in self.needs:
            self.needs[k] = max(0.0, self.needs[k] - Config.NEED_DECAY)

    def _zone_effect(self):
        if not self.zone:
            return
        for need, delta in ZONE_EFFECTS.get(self.zone.type, {}).items():
            self.needs[need] = min(10.0, self.needs[need] + delta)

    def _health_check(self):
        crit_count = sum(1 for v in self.needs.values() if v < Config.CRITICAL)

        if crit_count > 0:
            self.health -= 0.03 * crit_count
        else:
            self.health = min(Config.MAX_HEALTH, self.health + 0.01)

        if self.health <= 0:
            self.alive = False
            self.health = 0
            worst = min(self.needs, key=self.needs.get)
            self.death_reason = NEED_NAMES.get(worst, worst)
            self.path = []
            logger.warning(f"{self.name} DIED: {self.death_reason}")

    def _move(self):
        if not self.path or self.path_i >= len(self.path):
            return

        tx, ty = self.path[self.path_i]
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        dist = math.hypot(dx, dy)

        if dist < Config.MOVE_SPEED:
            self.pos = [float(tx), float(ty)]
            self.path_i += 1
            if self.path_i >= len(self.path):
                self.path = []
                self.goal = Goal.IDLE
                self.wait = 0
        else:
            self.pos[0] += (dx / dist) * Config.MOVE_SPEED
            self.pos[1] += (dy / dist) * Config.MOVE_SPEED

    def _detect_zone(self):
        for z in self.zones:
            if z.rect.collidepoint(self.pos[0], self.pos[1]):
                self.zone = z
                return
        self.zone = None

    def lowest_need(self) -> Tuple[str, float]:
        k = min(self.needs, key=self.needs.get)
        return k, self.needs[k]

    def state_for_ai(self) -> str:
        low_k, low_v = self.lowest_need()

        if low_v < Config.CRITICAL:
            status = "DYING"
            action = NEED_FIX[low_k]
        elif low_v < Config.LOW:
            status = "LOW"
            action = NEED_FIX[low_k]
        else:
            status = "OK"
            action = "any"

        needs_str = ", ".join(f"{k}:{v:.1f}" for k, v in self.needs.items())
        zone_now = self.zone.type.value if self.zone else "?"

        return (
            f"{self.id}: hp={self.health:.0f}, zone={zone_now}, "
            f"needs=[{needs_str}], worst={low_k}:{low_v:.1f}, "
            f"status={status}, fix={action}"
        )


class World:
    def __init__(self):
        self.zones = self._make_zones()
        self.graph = PathGraph(self.zones)
        self.agents = self._make_agents()
        self.tick_count = 0

    def _make_zones(self) -> List[Zone]:
        return [
            Zone("home_a", ZoneType.HOME, pygame.Rect(50, 70, 130, 130), Theme.ZONE_HOME),
            Zone("home_b", ZoneType.HOME, pygame.Rect(50, 260, 130, 130), Theme.ZONE_HOME),
            Zone("home_c", ZoneType.HOME, pygame.Rect(50, 450, 130, 130), Theme.ZONE_HOME),
            Zone("office", ZoneType.WORK, pygame.Rect(700, 140, 200, 180), Theme.ZONE_WORK),
            Zone("cafe", ZoneType.CAFE, pygame.Rect(400, 70, 170, 150), Theme.ZONE_CAFE),
            Zone("park", ZoneType.PARK, pygame.Rect(400, 450, 260, 180), Theme.ZONE_PARK),
            Zone("road", ZoneType.ROAD, pygame.Rect(260, 0, 50, 700), Theme.ZONE_ROAD),
        ]

    def _make_agents(self) -> Dict[str, Agent]:
        homes = [z for z in self.zones if z.type == ZoneType.HOME]
        agents = {
            "A": Agent("A", "Alice", Theme.BLUE, homes[0], self.graph),
            "B": Agent("B", "Bob", Theme.GREEN, homes[1], self.graph),
            "C": Agent("C", "Charlie", Theme.ORANGE, homes[2], self.graph),
        }
        for a in agents.values():
            a.zones = self.zones
        return agents

    def zone_by_type(self, zt: ZoneType) -> Optional[Zone]:
        for z in self.zones:
            if z.type == zt:
                return z
        return None

    def update(self):
        self.tick_count += 1
        for agent in self.agents.values():
            agent.tick()


class Brain:
    def __init__(self, world: World):
        self.world = world
        self.session: Optional[aiohttp.ClientSession] = None
        self.raw = ""
        self.busy = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.LLM_TIMEOUT))
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()

    async def decide(self):
        if self.busy:
            return
        self.busy = True

        try:
            prompt = self._prompt()
            self.raw = await self._ask(prompt)
            self._parse(self.raw)
        except Exception as e:
            logger.error(f"Brain: {e}")
            self.raw = str(e)
        finally:
            self.busy = False

    def _prompt(self) -> str:
        agents_lines = [a.state_for_ai() for a in self.world.agents.values() if a.alive]

        return f"""You control agents. Each has 4 needs: hunger, energy, social, work.
If ANY need drops below 2.5, agent LOSES HEALTH and will DIE.

HOW TO FIX EACH NEED:
- hunger < 4 → go_cafe (cafe restores hunger)
- energy < 4 → go_home (home restores energy)
- social < 4 → go_park (park restores social)
- work < 4 → go_work (office restores work)

CRITICAL RULE: If status=DYING, agent MUST go to the zone shown in "fix=" field!

AGENTS NOW:
{chr(10).join(agents_lines)}

AVAILABLE GOALS: idle, go_home, go_cafe, go_park, go_work

Reply ONLY JSON:
{{"A":{{"goal":"..."}},"B":{{"goal":"..."}},"C":{{"goal":"..."}}}}"""

    async def _ask(self, prompt: str) -> str:
        body = {
            "prompt": f"<|im_start|>system\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
            "n_predict": 120,
            "temperature": 0.25,
            "stop": ["<|im_end|>"],
            "stream": False,
        }
        async with self.session.post(Config.LLM_URL, json=body) as r:
            if r.status == 200:
                return (await r.json()).get("content", "")
            raise RuntimeError(f"HTTP {r.status}")

    def _parse(self, text: str):
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return

        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return

        goal_map = {
            "idle": Goal.IDLE,
            "go_home": Goal.GO_HOME,
            "go_work": Goal.GO_WORK,
            "go_cafe": Goal.GO_CAFE,
            "go_park": Goal.GO_PARK,
        }

        for aid, act in data.items():
            if aid not in self.world.agents:
                continue

            agent = self.world.agents[aid]
            if not agent.alive:
                continue

            raw_goal = str(act.get("goal", "")).strip().lower()
            goal = goal_map.get(raw_goal)

            if not goal:
                continue

            if goal == Goal.IDLE:
                continue

            zone_type = ZONE_FOR_GOAL.get(goal)
            if not zone_type:
                continue

            if goal == Goal.GO_HOME:
                target = agent.home
            else:
                target = self.world.zone_by_type(zone_type)

            if target:
                agent.assign(goal, target)


class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.f_sm = pygame.font.SysFont("Arial", 12)
        self.f_md = pygame.font.SysFont("Arial", 14)
        self.f_lg = pygame.font.SysFont("Arial", 17)
        self.f_xl = pygame.font.SysFont("Arial", 20)

    def draw(self, world: World, brain: Brain):
        self.screen.fill(Theme.BG)
        self._zones(world.zones)
        self._agents(world.agents)
        self._panel(world, brain)
        pygame.display.flip()

    def _zones(self, zones: List[Zone]):
        for z in zones:
            pygame.draw.rect(self.screen, z.color, z.rect, border_radius=10)
            pygame.draw.rect(self.screen, Theme.BORDER, z.rect, 1, border_radius=10)
            lbl = self.f_sm.render(z.name, True, Theme.TEXT_DIM)
            self.screen.blit(lbl, (z.rect.x + 6, z.rect.y + 4))

    def _agents(self, agents: Dict[str, Agent]):
        for a in agents.values():
            x, y = int(a.pos[0]), int(a.pos[1])

            if a.path and a.alive:
                pts = [(x, y)] + a.path[a.path_i:]
                if len(pts) > 1:
                    pygame.draw.lines(self.screen, a.color, False, pts, 2)

            col = Theme.TEXT_MUTED if not a.alive else a.color
            pygame.draw.circle(self.screen, col, (x, y), 14)
            pygame.draw.circle(self.screen, Theme.TEXT, (x, y), 14, 2)

            if not a.alive:
                pygame.draw.line(self.screen, Theme.RED, (x - 5, y - 5), (x + 5, y + 5), 2)
                pygame.draw.line(self.screen, Theme.RED, (x + 5, y - 5), (x - 5, y + 5), 2)

            nm = self.f_sm.render(a.name, True, Theme.TEXT)
            self.screen.blit(nm, (x - nm.get_width() // 2, y - 28))

            if a.thought and a.alive:
                self._bubble(a.thought, x, y - 44)

    def _bubble(self, text: str, x: int, y: int):
        s = self.f_sm.render(text[:28], True, Theme.TEXT)
        w, h = s.get_width() + 10, s.get_height() + 5
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (35, 35, 40, 230), bg.get_rect(), border_radius=6)
        self.screen.blit(bg, (x - w // 2, y - h // 2))
        self.screen.blit(s, (x - s.get_width() // 2, y - s.get_height() // 2))

    def _panel(self, world: World, brain: Brain):
        px = Config.SCREEN_WIDTH - 370
        panel = pygame.Surface((370, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
        panel.fill((26, 26, 30, 250))
        self.screen.blit(panel, (px, 0))
        pygame.draw.line(self.screen, Theme.BORDER, (px, 0), (px, Config.SCREEN_HEIGHT))

        y = 16
        col = Theme.ORANGE if brain.busy else Theme.GREEN
        pygame.draw.circle(self.screen, col, (px + 16, y + 9), 5)
        lbl = self.f_xl.render("AI: " + ("..." if brain.busy else "OK"), True, Theme.TEXT)
        self.screen.blit(lbl, (px + 30, y))
        y += 35

        tick = self.f_sm.render(f"Tick: {world.tick_count}", True, Theme.TEXT_MUTED)
        self.screen.blit(tick, (px + 16, y))
        y += 25

        for agent in world.agents.values():
            y = self._card(agent, px + 10, y) + 10

        y += 10
        self._log(brain, px + 10, y)

    def _card(self, a: Agent, x: int, y: int) -> int:
        h = 110 if a.alive else 45
        card = pygame.Surface((350, h), pygame.SRCALPHA)
        pygame.draw.rect(card, Theme.CARD, card.get_rect(), border_radius=8)
        pygame.draw.rect(card, Theme.BORDER, card.get_rect(), 1, border_radius=8)
        self.screen.blit(card, (x, y))

        col = Theme.TEXT_MUTED if not a.alive else a.color
        pygame.draw.circle(self.screen, col, (x + 16, y + 16), 6)

        nm = self.f_lg.render(a.name, True, Theme.TEXT)
        self.screen.blit(nm, (x + 30, y + 8))

        if not a.alive:
            d = self.f_sm.render(f"DEAD: {a.death_reason}", True, Theme.RED)
            self.screen.blit(d, (x + 10, y + 28))
            return y + h

        hp_col = Theme.RED if a.health < 50 else (Theme.ORANGE if a.health < 75 else Theme.GREEN)
        info = f"HP:{a.health:.0f}% | {a.goal.value} | {a.zone.type.value if a.zone else '?'}"
        self.screen.blit(self.f_sm.render(info, True, hp_col), (x + 90, y + 10))

        by = y + 32
        for need, val in a.needs.items():
            c = Theme.RED if val < Config.CRITICAL else (Theme.ORANGE if val < Config.LOW else Theme.GREEN)
            pygame.draw.rect(self.screen, (45, 45, 50), (x + 10, by, 165, 6), border_radius=3)
            pygame.draw.rect(self.screen, c, (x + 10, by, val * 16.5, 6), border_radius=3)
            lbl = self.f_sm.render(f"{NEED_NAMES[need]}: {val:.1f}", True, Theme.TEXT_DIM)
            self.screen.blit(lbl, (x + 185, by - 3))
            by += 18

        return y + h

    def _log(self, brain: Brain, x: int, y: int):
        lbl = self.f_md.render("LLM:", True, Theme.TEXT_DIM)
        self.screen.blit(lbl, (x, y))
        y += 18

        text = brain.raw[:300] if brain.raw else "..."
        line_x = x
        for word in text.split():
            s = self.f_sm.render(word + " ", True, Theme.TEXT_MUTED)
            if line_x + s.get_width() > Config.SCREEN_WIDTH - 20:
                line_x = x
                y += 14
            self.screen.blit(s, (line_x, y))
            line_x += s.get_width()


class Simulation:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        pygame.display.set_caption("AI Life Sim")
        self.clock = pygame.time.Clock()
        self.world = World()
        self.renderer = Renderer(self.screen)
        self.running = True

    async def run(self):
        async with Brain(self.world) as brain:
            while self.running:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self.running = False

                self.world.update()

                if self.world.tick_count % Config.AI_THINK_INTERVAL == 0:
                    asyncio.create_task(brain.decide())

                self.renderer.draw(self.world, brain)
                self.clock.tick(Config.FPS)
                await asyncio.sleep(0)

        pygame.quit()


if __name__ == "__main__":
    asyncio.run(Simulation().run())
