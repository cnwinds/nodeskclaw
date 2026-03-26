"""GeneHub Registry HTTP client & GeneHubAdapter.

Contains both the legacy module-level functions (deprecated, will be removed
after gene_service migration) and the new GeneHubAdapter implementing the
RegistryAdapter interface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.registry_adapter import (
    RegistryAdapter,
    RegistrySearchResult,
    RegistrySkillDetail,
    RegistrySkillItem,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_client: httpx.AsyncClient | None = None


def _is_enabled() -> bool:
    return bool(settings.GENEHUB_REGISTRY_URL)


def _base_url() -> str:
    return settings.GENEHUB_REGISTRY_URL.rstrip("/")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if settings.GENEHUB_API_KEY:
        h["Authorization"] = f"Bearer {settings.GENEHUB_API_KEY}"
    return h


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers())
    return _client


def _log_error(method: str, path: str, exc: Exception) -> None:
    if isinstance(exc, httpx.TimeoutException):
        logger.warning("GeneHub timeout: %s %s", method, path)
    elif isinstance(exc, httpx.HTTPStatusError):
        logger.warning("GeneHub HTTP %d: %s %s", exc.response.status_code, method, path)
    elif isinstance(exc, httpx.RequestError):
        logger.warning("GeneHub connection error: %s %s -> %s", method, path, exc)
    else:
        logger.warning("GeneHub unexpected error: %s %s -> %s", method, path, exc)


async def _get(path: str, params: dict[str, Any] | None = None) -> dict | None:
    if not _is_enabled():
        return None
    try:
        client = await _get_client()
        resp = await client.get(f"{_base_url()}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            logger.warning("GeneHub API error: %s %s -> %s", path, params, body.get("message"))
            return None
        return body
    except Exception as e:
        _log_error("GET", path, e)
        return None


async def _post(path: str, json_body: dict | None = None) -> dict | None:
    if not _is_enabled():
        return None
    try:
        client = await _get_client()
        resp = await client.post(f"{_base_url()}{path}", json=json_body or {})
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            logger.warning("GeneHub API error: POST %s -> %s", path, body.get("message"))
            return None
        return body
    except Exception as e:
        _log_error("POST", path, e)
        return None


# ═══════════════════════════════════════════════════
#  Gene Market APIs
# ═══════════════════════════════════════════════════


async def list_genes(
    *,
    keyword: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    sort: str = "popularity",
    page: int = 1,
    page_size: int = 20,
) -> dict | None:
    """GET /api/v1/genes — returns full response body or None."""
    sort_map = {"popularity": "popular", "rating": "rating", "newest": "newest"}
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
    }
    if keyword:
        params["q"] = keyword
    if tag:
        params["tags"] = tag
    if category:
        params["category"] = category
    params["sort"] = sort_map.get(sort, sort)
    return await _get("/api/v1/genes", params)


async def get_gene(slug: str) -> dict | None:
    """GET /api/v1/genes/:slug — returns gene data or None."""
    body = await _get(f"/api/v1/genes/{slug}")
    return body.get("data") if body else None


async def get_manifest(slug: str, version: str | None = None) -> dict | None:
    """GET /api/v1/genes/:slug/manifest — returns manifest dict or None."""
    params = {"version": version} if version else None
    body = await _get(f"/api/v1/genes/{slug}/manifest", params)
    return body.get("data") if body else None


async def get_featured_genes(limit: int = 10) -> list[dict] | None:
    """GET /api/v1/genes/featured"""
    body = await _get("/api/v1/genes/featured", {"limit": limit})
    return body.get("data") if body else None


async def get_gene_tags() -> list[dict] | None:
    """GET /api/v1/genes/tags"""
    body = await _get("/api/v1/genes/tags")
    return body.get("data") if body else None


async def get_gene_synergies(slug: str) -> list[dict] | None:
    """GET /api/v1/genes/:slug/synergies"""
    body = await _get(f"/api/v1/genes/{slug}/synergies")
    return body.get("data") if body else None


# ═══════════════════════════════════════════════════
#  Genome Market APIs
# ═══════════════════════════════════════════════════


async def list_genomes(
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict | None:
    """GET /api/v1/genomes"""
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if keyword:
        params["q"] = keyword
    return await _get("/api/v1/genomes", params)


async def get_genome(slug: str) -> dict | None:
    """GET /api/v1/genomes/:slug"""
    body = await _get(f"/api/v1/genomes/{slug}")
    return body.get("data") if body else None


async def get_featured_genomes(limit: int = 10) -> list[dict] | None:
    """GET /api/v1/genomes/featured"""
    body = await _get("/api/v1/genomes/featured", {"limit": limit})
    return body.get("data") if body else None


# ═══════════════════════════════════════════════════
#  Write-back APIs
# ═══════════════════════════════════════════════════


async def report_install(slug: str) -> bool:
    """POST /api/v1/genes/:slug/installed"""
    result = await _post(f"/api/v1/genes/{slug}/installed")
    return result is not None


async def report_effectiveness(slug: str, metric_type: str, value: float) -> bool:
    """POST /api/v1/genes/:slug/effectiveness"""
    result = await _post(
        f"/api/v1/genes/{slug}/effectiveness",
        {"metric_type": metric_type, "value": value},
    )
    return result is not None


async def publish_gene(manifest: dict) -> dict | None:
    """POST /api/v1/genes — push a new gene to GeneHub."""
    body = await _post("/api/v1/genes", {"manifest": manifest})
    return body.get("data") if body else None


async def publish_genome(manifest: dict) -> dict | None:
    """POST /api/v1/genomes — push a new genome to GeneHub."""
    body = await _post("/api/v1/genomes", {"manifest": manifest})
    return body.get("data") if body else None


async def close() -> None:
    """Shutdown the shared HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


# ═══════════════════════════════════════════════════
#  GeneHubAdapter — RegistryAdapter implementation
# ═══════════════════════════════════════════════════


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _extract_paginated(body: dict[str, Any]) -> tuple[list[dict], int]:
    data = body.get("data", {})
    if isinstance(data, dict):
        return data.get("items", []), data.get("total", 0)
    if isinstance(data, list):
        return data, len(data)
    return [], 0


class GeneHubAdapter(RegistryAdapter):
    """Adapter for registries that speak the GeneHub ``/api/v1/genes/*`` protocol.

    Reusable for DeskHub and any future registry that aligns with the same API.
    """

    _TIMEOUT = 5.0
    _SORT_MAP = {"popularity": "popular", "rating": "rating", "newest": "newest"}
    _SORT_MAP_SKILLS = {"popularity": "downloads", "rating": "stars", "newest": "newest"}

    def __init__(
        self,
        *,
        registry_id: str,
        registry_name: str,
        base_url: str,
        api_key: str = "",
    ) -> None:
        super().__init__(
            registry_id=registry_id,
            registry_name=registry_name,
            base_url=base_url,
        )
        self._api_key = api_key
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = httpx.AsyncClient(timeout=self._TIMEOUT, headers=headers)
        self._api_mode = "auto"

    def _url(self, path: str) -> str:
        assert self.base_url is not None
        return f"{self.base_url.rstrip('/')}{path}"

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict | None = None,
    ) -> tuple[int | None, dict | None]:
        try:
            if method == "GET":
                resp = await self._http.get(self._url(path), params=params)
            else:
                resp = await self._http.post(self._url(path), json=json_body or {})
            status = resp.status_code
            try:
                parsed = resp.json()
            except Exception:
                parsed = None
            body = parsed if isinstance(parsed, dict) else None
            return status, body
        except Exception as e:
            self._log_error(method, path, e)
            return None, None

    @staticmethod
    def _is_genes_ok(body: dict | None) -> bool:
        return isinstance(body, dict) and body.get("code") == 0

    @staticmethod
    def _is_skills_ok(body: dict | None) -> bool:
        return isinstance(body, dict) and body.get("success") is True

    async def _detect_api_mode(self) -> str:
        if self._api_mode != "auto":
            return self._api_mode

        genes_status, genes_body = await self._request_json(
            "GET",
            "/api/v1/genes",
            params={"page": 1, "page_size": 1, "sort": "popular"},
        )
        if genes_status not in (None, 404) and (
            self._is_genes_ok(genes_body)
            or (isinstance(genes_body, dict) and "code" in genes_body)
        ):
            self._api_mode = "genes"
            logger.info("%s detected registry protocol: genes", self.registry_name)
            return self._api_mode

        skills_status, skills_body = await self._request_json(
            "GET",
            "/api/v1/skills",
            params={"page": 1, "limit": 1, "sort": "downloads"},
        )
        if skills_status not in (None, 404) and (
            self._is_skills_ok(skills_body)
            or (isinstance(skills_body, dict) and "success" in skills_body)
        ):
            self._api_mode = "skills"
            logger.info("%s detected registry protocol: skills", self.registry_name)
            return self._api_mode

        self._api_mode = "genes"
        logger.warning("%s protocol detection failed, fallback to genes", self.registry_name)
        return self._api_mode

    def _gene_to_item(self, gene: dict[str, Any]) -> RegistrySkillItem:
        return RegistrySkillItem(
            slug=gene.get("slug", ""),
            name=gene.get("name", ""),
            description=gene.get("description"),
            short_description=gene.get("short_description"),
            version=gene.get("version"),
            tags=gene.get("tags") or [],
            category=gene.get("category"),
            source=gene.get("source", "official"),
            source_ref=gene.get("source_ref"),
            icon=gene.get("icon"),
            install_count=gene.get("install_count", 0),
            avg_rating=gene.get("avg_rating", 0),
            effectiveness_score=gene.get("effectiveness_score", 0),
            is_featured=gene.get("is_featured", gene.get("install_count", 0) > 0),
            review_status=gene.get("review_status", "approved"),
            is_published=gene.get("is_published", True),
            manifest=gene.get("manifest"),
            dependencies=gene.get("dependencies") or [],
            synergies=gene.get("synergies") or [],
            parent_gene_id=gene.get("parent_gene_id"),
            created_by_instance_id=gene.get("created_by_instance_id"),
            created_by=gene.get("created_by"),
            org_id=gene.get("org_id"),
            visibility=gene.get("visibility", "public"),
            created_at=_parse_dt(gene.get("created_at")),
            updated_at=_parse_dt(gene.get("updated_at")),
            source_registry=self.registry_id,
            source_registry_name=self.registry_name,
        )

    def _skill_to_item(self, skill: dict[str, Any]) -> RegistrySkillItem:
        owner = skill.get("owner") or {}
        latest_version = skill.get("latestVersion") or {}
        return RegistrySkillItem(
            slug=skill.get("slug", ""),
            name=skill.get("displayName") or skill.get("name", ""),
            description=skill.get("summary"),
            short_description=skill.get("summary"),
            version=latest_version.get("version") or skill.get("version"),
            tags=skill.get("tags") or [],
            category=None,
            source=skill.get("sourceLabel") or "official",
            source_ref=skill.get("sourceUrl"),
            icon=skill.get("icon"),
            install_count=skill.get("statsDownloads", 0),
            avg_rating=float(skill.get("statsStars", 0) or 0),
            effectiveness_score=skill.get("qualityScore", 0),
            is_featured=False,
            review_status=skill.get("moderationStatus"),
            is_published=skill.get("softDeletedAt") is None,
            manifest=(skill.get("manifest") if isinstance(skill.get("manifest"), dict) else None),
            dependencies=skill.get("dependencies") or [],
            synergies=skill.get("synergies") or [],
            parent_gene_id=None,
            created_by_instance_id=None,
            created_by=owner.get("handle") or skill.get("ownerHandle"),
            org_id=skill.get("orgId"),
            visibility=skill.get("visibility", "public"),
            created_at=_parse_dt(skill.get("createdAt")),
            updated_at=_parse_dt(skill.get("updatedAt")),
            source_registry=self.registry_id,
            source_registry_name=self.registry_name,
        )

    @staticmethod
    def _extract_skills_paginated(body: dict[str, Any]) -> tuple[list[dict], int]:
        data = body.get("data", {})
        if isinstance(data, dict):
            items = data.get("items", [])
            total = data.get("total", 0)
            if isinstance(items, list):
                return items, int(total or len(items))
        if isinstance(data, list):
            return data, len(data)
        return [], 0

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict | None:
        try:
            resp = await self._http.get(self._url(path), params=params)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                logger.warning(
                    "%s API error: GET %s -> %s",
                    self.registry_name, path, body.get("message"),
                )
                return None
            return body
        except Exception as e:
            self._log_error("GET", path, e)
            return None

    async def _post(self, path: str, json_body: dict | None = None) -> dict | None:
        try:
            resp = await self._http.post(self._url(path), json=json_body or {})
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                logger.warning(
                    "%s API error: POST %s -> %s",
                    self.registry_name, path, body.get("message"),
                )
                return None
            return body
        except Exception as e:
            self._log_error("POST", path, e)
            return None

    def _log_error(self, method: str, path: str, exc: Exception) -> None:
        if isinstance(exc, httpx.TimeoutException):
            logger.warning("%s timeout: %s %s", self.registry_name, method, path)
        elif isinstance(exc, httpx.HTTPStatusError):
            logger.warning(
                "%s HTTP %d: %s %s",
                self.registry_name, exc.response.status_code, method, path,
            )
        elif isinstance(exc, httpx.RequestError):
            logger.warning(
                "%s connection error: %s %s -> %s",
                self.registry_name, method, path, exc,
            )
        else:
            logger.warning(
                "%s unexpected error: %s %s -> %s",
                self.registry_name, method, path, exc,
            )

    # ── RegistryAdapter interface ──

    async def search_skills(
        self,
        *,
        keyword: str | None = None,
        tag: str | None = None,
        category: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        org_id: str | None = None,
        sort: str = "popularity",
        page: int = 1,
        page_size: int = 20,
    ) -> RegistrySearchResult | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            params: dict[str, Any] = {"page": page, "limit": page_size}
            if keyword:
                params["q"] = keyword
            if tag:
                params["tags"] = tag
            params["sort"] = self._SORT_MAP_SKILLS.get(sort, sort)
            status, body = await self._request_json("GET", "/api/v1/skills", params=params)
            if status == 404:
                self._api_mode = "genes"
                return await self.search_skills(
                    keyword=keyword, tag=tag, category=category, source=source,
                    visibility=visibility, org_id=org_id, sort=sort, page=page, page_size=page_size,
                )
            if not self._is_skills_ok(body):
                return None
            raw_items, total = self._extract_skills_paginated(body or {})
            items = [self._skill_to_item(item) for item in raw_items]
            return RegistrySearchResult(items=items, total=total)

        params = {"page": page, "page_size": page_size}
        if keyword:
            params["q"] = keyword
        if tag:
            params["tags"] = tag
        if category:
            params["category"] = category
        params["sort"] = self._SORT_MAP.get(sort, sort)
        body = await self._get("/api/v1/genes", params)
        if body is None:
            return None
        raw_items, total = _extract_paginated(body)
        items = [self._gene_to_item(item) for item in raw_items]
        return RegistrySearchResult(items=items, total=total)

    async def get_skill(self, slug: str) -> RegistrySkillDetail | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            status, body = await self._request_json("GET", f"/api/v1/skills/{slug}")
            if self._is_skills_ok(body):
                data = body.get("data")
                if not isinstance(data, dict):
                    return None
                item = self._skill_to_item(data)
                return RegistrySkillDetail(**item.model_dump())
            if status == 404:
                status, body = await self._request_json(
                    "GET",
                    "/api/v1/skills",
                    params={"q": slug, "page": 1, "limit": 20, "sort": "downloads"},
                )
                if self._is_skills_ok(body):
                    raw_items, _ = self._extract_skills_paginated(body or {})
                    for raw_item in raw_items:
                        if raw_item.get("slug") == slug:
                            item = self._skill_to_item(raw_item)
                            return RegistrySkillDetail(**item.model_dump())
            return None

        body = await self._get(f"/api/v1/genes/{slug}")
        data = body.get("data") if body else None
        if not data:
            return None
        item = self._gene_to_item(data)
        return RegistrySkillDetail(**item.model_dump())

    async def get_manifest(self, slug: str, version: str | None = None) -> dict | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            params = {"version": version} if version else None
            _status, body = await self._request_json(
                "GET",
                f"/api/v1/skills/{slug}/manifest",
                params=params,
            )
            if self._is_skills_ok(body):
                data = body.get("data")
                return data if isinstance(data, dict) else None

            _status, detail_body = await self._request_json("GET", f"/api/v1/skills/{slug}")
            if self._is_skills_ok(detail_body):
                detail_data = detail_body.get("data")
                if not isinstance(detail_data, dict):
                    return None
                manifest = detail_data.get("manifest")
                if isinstance(manifest, dict):
                    return manifest
                latest_version = detail_data.get("latestVersion")
                if isinstance(latest_version, dict):
                    latest_manifest = latest_version.get("manifest")
                    if isinstance(latest_manifest, dict):
                        return latest_manifest
            return None

        params = {"version": version} if version else None
        body = await self._get(f"/api/v1/genes/{slug}/manifest", params)
        return body.get("data") if body else None

    async def get_featured(self, limit: int = 10) -> list[RegistrySkillItem] | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            _status, body = await self._request_json(
                "GET",
                "/api/v1/skills",
                params={"page": 1, "limit": limit, "sort": "downloads"},
            )
            if not self._is_skills_ok(body):
                return None
            raw_items, _ = self._extract_skills_paginated(body or {})
            return [self._skill_to_item(item) for item in raw_items[:limit]]

        body = await self._get("/api/v1/genes/featured", {"limit": limit})
        data = body.get("data") if body else None
        if not data or not isinstance(data, list):
            return None
        return [self._gene_to_item(g) for g in data]

    async def get_tags(self) -> list[dict] | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            tag_counts: dict[str, int] = {}
            page = 1
            limit = 100
            while page <= 3:
                _status, body = await self._request_json(
                    "GET",
                    "/api/v1/skills",
                    params={"page": page, "limit": limit, "sort": "downloads"},
                )
                if not self._is_skills_ok(body):
                    return None
                raw_items, total = self._extract_skills_paginated(body or {})
                for raw_item in raw_items:
                    raw_tags = raw_item.get("tags")
                    if isinstance(raw_tags, list):
                        for tag in raw_tags:
                            if isinstance(tag, str) and tag:
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                if len(raw_items) < limit or page * limit >= total:
                    break
                page += 1
            return [
                {"tag": tag, "count": count}
                for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
            ]

        body = await self._get("/api/v1/genes/tags")
        return body.get("data") if body else None

    async def get_synergies(self, slug: str) -> list[dict] | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            return None
        body = await self._get(f"/api/v1/genes/{slug}/synergies")
        return body.get("data") if body else None

    async def publish_skill(self, manifest: dict) -> dict | None:
        mode = await self._detect_api_mode()
        if mode == "skills":
            _status, body = await self._request_json(
                "POST",
                "/api/v1/skills",
                json_body={"manifest": manifest},
            )
            if not self._is_skills_ok(body):
                return None
            data = body.get("data")
            return data if isinstance(data, dict) else {}

        body = await self._post("/api/v1/genes", {"manifest": manifest})
        return body.get("data") if body else None

    async def report_install(self, slug: str) -> bool:
        mode = await self._detect_api_mode()
        if mode == "skills":
            for path in (
                f"/api/v1/skills/{slug}/installed",
                f"/api/v1/skills/{slug}/install",
            ):
                status, body = await self._request_json("POST", path, json_body={})
                if self._is_skills_ok(body):
                    return True
                if status not in (404, 405):
                    return False
            return False

        result = await self._post(f"/api/v1/genes/{slug}/installed")
        return result is not None

    async def report_effectiveness(
        self, slug: str, metric_type: str, value: float
    ) -> bool:
        mode = await self._detect_api_mode()
        if mode == "skills":
            payload = {"metric_type": metric_type, "value": value}
            for path in (
                f"/api/v1/skills/{slug}/effectiveness",
                f"/api/v1/skills/{slug}/metrics",
            ):
                status, body = await self._request_json(
                    "POST",
                    path,
                    json_body=payload,
                )
                if self._is_skills_ok(body):
                    return True
                if status not in (404, 405):
                    return False
            return False

        result = await self._post(
            f"/api/v1/genes/{slug}/effectiveness",
            {"metric_type": metric_type, "value": value},
        )
        return result is not None

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
