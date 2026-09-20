from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import Locator as PWLocator
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from banking_gpt.models import (
    ActionType,
    InteractiveElement,
    Locator,
    LocatorStrategy,
    Observation,
    ProposedAction,
    Target,
)


class SurfaceError(RuntimeError):
    pass


class TargetNotFound(SurfaceError):
    pass


class AmbiguousTarget(SurfaceError):
    pass


class SurfaceAdapter(ABC):
    @abstractmethod
    async def start(self, target: Target) -> None: ...

    @abstractmethod
    async def observe(self, screenshot_path: Path | None = None) -> Observation: ...

    @abstractmethod
    async def execute(self, action: ProposedAction) -> Any: ...

    @abstractmethod
    async def is_visible(self, locator: Locator, timeout_ms: int = 500) -> bool: ...

    @abstractmethod
    async def capture_screenshot(self, path: Path) -> None: ...

    @abstractmethod
    async def close(self, trace_path: Path | None = None) -> None: ...


class PlaywrightBrowserAdapter(SurfaceAdapter):
    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 5_000,
        slow_mo_ms: int = 0,
        close_delay_seconds: float = 0,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.slow_mo_ms = slow_mo_ms
        self.close_delay_seconds = close_delay_seconds
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._tracing = False

    @property
    def page(self) -> Page:
        if self._page is None:
            raise SurfaceError("Browser surface has not been started")
        return self._page

    async def start(self, target: Target) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
        )
        self._context = await self._browser.new_context()
        await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._tracing = True
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        await self._page.goto(str(target.entry_point), wait_until="domcontentloaded")

    async def observe(self, screenshot_path: Path | None = None) -> Observation:
        if screenshot_path:
            await self.capture_screenshot(screenshot_path)

        raw_elements = await self.page.locator(
            "button, input, select, textarea, a[href], [role]"
        ).evaluate_all(
            """
            elements => elements
              .filter(el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' && style.display !== 'none'
                  && rect.width > 0 && rect.height > 0;
              })
              .map((el, index) => {
                const tag = el.tagName.toLowerCase();
                let role = el.getAttribute('role');
                if (!role && tag === 'button') role = 'button';
                if (!role && tag === 'a') role = 'link';
                if (!role && tag === 'select') role = 'combobox';
                if (!role && tag === 'textarea') role = 'textbox';
                if (!role && tag === 'input') {
                  const type = (el.getAttribute('type') || 'text').toLowerCase();
                  role = ['submit', 'button'].includes(type) ? 'button' : 'textbox';
                }
                const label = el.labels && el.labels.length
                  ? Array.from(el.labels).map(item => item.innerText).join(' ')
                  : '';
                return {
                  role: role || tag,
                  name: (el.getAttribute('aria-label') || label || el.innerText
                    || el.getAttribute('value') || el.getAttribute('placeholder') || '').trim(),
                  element_id: el.id || `generated-${index}`
                };
              })
            """
        )

        return Observation(
            url=self.page.url,
            title=await self.page.title(),
            visible_text=(await self.page.locator("body").inner_text())[:12_000],
            elements=[InteractiveElement.model_validate(item) for item in raw_elements],
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        )

    async def execute(self, action: ProposedAction) -> Any:
        if action.action == ActionType.NAVIGATE:
            await self.page.goto(action.value or "", wait_until="domcontentloaded")
            return None
        if action.action in {ActionType.COMPLETE, ActionType.REQUEST_HELP}:
            return None

        target = await self.resolve(action.target)
        if action.action == ActionType.CLICK:
            await target.click()
            return None
        if action.action == ActionType.FILL:
            await target.fill(action.value or "")
            return None
        if action.action == ActionType.EXTRACT:
            return (await target.inner_text()).strip()
        if action.action == ActionType.VERIFY:
            return await target.is_visible()
        raise SurfaceError(f"Unsupported action: {action.action}")

    async def resolve(self, candidates: list[Locator]) -> PWLocator:
        failures: list[str] = []
        for candidate in sorted(candidates, key=lambda item: item.priority):
            locator = self._to_playwright_locator(candidate)
            try:
                count = await locator.count()
                if count == 1:
                    await locator.wait_for(state="visible", timeout=self.timeout_ms)
                    return locator
                if count > 1:
                    failures.append(f"{candidate.strategy}:{candidate.value} matched {count}")
                else:
                    failures.append(f"{candidate.strategy}:{candidate.value} matched 0")
            except PlaywrightTimeoutError:
                failures.append(f"{candidate.strategy}:{candidate.value} was not visible")
        if any("matched 2" in failure or "matched 3" in failure for failure in failures):
            raise AmbiguousTarget("; ".join(failures))
        raise TargetNotFound("; ".join(failures))

    def _to_playwright_locator(self, locator: Locator) -> PWLocator:
        if locator.strategy == LocatorStrategy.ROLE:
            return self.page.get_by_role(
                locator.value, name=locator.name, exact=locator.exact
            )
        if locator.strategy == LocatorStrategy.LABEL:
            return self.page.get_by_label(locator.value, exact=locator.exact)
        if locator.strategy == LocatorStrategy.TEXT:
            return self.page.get_by_text(locator.value, exact=locator.exact)
        if locator.strategy == LocatorStrategy.TEST_ID:
            return self.page.get_by_test_id(locator.value)
        return self.page.locator(locator.value)

    async def is_visible(self, locator: Locator, timeout_ms: int = 500) -> bool:
        try:
            await self._to_playwright_locator(locator).first.wait_for(
                state="visible", timeout=timeout_ms
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def capture_screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=True)

    async def manual_takeover(self) -> None:
        if self.headless:
            raise SurfaceError("Manual takeover requires a headed browser")
        await self.page.bring_to_front()

    async def close(self, trace_path: Path | None = None) -> None:
        if self.close_delay_seconds:
            await asyncio.sleep(self.close_delay_seconds)
        if self._context and self._tracing:
            await self._context.tracing.stop(path=str(trace_path) if trace_path else None)
            self._tracing = False
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
