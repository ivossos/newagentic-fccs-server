"""FCCS HTTP Client - Async client for Oracle FCCS REST API."""

import base64
from typing import Any, Optional
from urllib.parse import quote

import httpx

from fccs_agent.config import FCCSConfig
from fccs_agent.client.mock_data import (
    MOCK_APPLICATIONS,
    MOCK_JOBS,
    MOCK_JOB_STATUS,
    MOCK_RULE_RESULT,
    MOCK_DIMENSIONS,
    MOCK_MEMBERS,
    MOCK_DATA_RULE_RESULT,
    MOCK_DATA_SLICE,
)
from fccs_agent.utils.cache import (
    load_members_from_cache,
    save_members_to_cache,
)


class FccsClient:
    """Async HTTP client for Oracle FCCS REST API."""

    def __init__(self, config: FCCSConfig):
        self.config = config
        self.admin_mode = False
        self._client: Optional[httpx.AsyncClient] = None
        self._fcm_client: Optional[httpx.AsyncClient] = None

        if not config.fccs_mock_mode:
            if not all([config.fccs_url, config.fccs_username, config.fccs_password]):
                raise ValueError(
                    "Missing FCCS credentials (URL, USERNAME, PASSWORD) required for real connection."
                )

            # Basic Auth header
            auth_string = f"{config.fccs_username}:{config.fccs_password}"
            auth_header = base64.b64encode(auth_string.encode()).decode()

            base_url = f"{config.fccs_url}/HyperionPlanning/rest/{config.fccs_api_version}/applications"
            fcm_base_url = f"{config.fccs_url}/HyperionPlanning/rest/fcmapi/v1"

            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/json",
            }

            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=60.0,
            )

            self._fcm_client = httpx.AsyncClient(
                base_url=fcm_base_url,
                headers=headers,
                timeout=60.0,
            )

    async def close(self):
        """Close HTTP clients."""
        if self._client:
            await self._client.aclose()
        if self._fcm_client:
            await self._fcm_client.aclose()

    def _get_query_params(self, has_existing_query: bool = False) -> str:
        """Get admin mode query parameter if needed."""
        if not self.admin_mode:
            return ""
        return "&adminMode=true" if has_existing_query else "?adminMode=true"

    # ========== Application Methods ==========

    async def get_applications(self) -> dict[str, Any]:
        """Get FCCS applications / Obter aplicacoes FCCS."""
        if self.config.fccs_mock_mode:
            return MOCK_APPLICATIONS

        response = await self._client.get("/")
        response.raise_for_status()
        data = response.json()

        # Check if application is in admin mode
        if data.get("items") and len(data["items"]) > 0:
            if data["items"][0].get("adminMode"):
                self.admin_mode = True

        return data

    async def get_rest_api_version(self) -> dict[str, Any]:
        """Get REST API version / Obter versao da API REST."""
        if self.config.fccs_mock_mode:
            return {"version": self.config.fccs_api_version, "apiVersion": "3.0"}

        # Try version endpoints
        for endpoint in ["/rest/version", "/version", "/api/version"]:
            try:
                response = await self._client.get(endpoint)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                continue

        return {
            "version": self.config.fccs_api_version,
            "note": "Version endpoint not available, using configured version"
        }

    # ========== Job Methods ==========

    async def list_jobs(self, app_name: str) -> dict[str, Any]:
        """List jobs / Listar trabalhos."""
        if self.config.fccs_mock_mode:
            return MOCK_JOBS

        try:
            response = await self._client.get(
                f"/{app_name}/jobs{self._get_query_params()}"
            )
            if response.status_code == 200:
                return response.json()
            return {"items": []}
        except Exception as e:
            return {"items": [], "error": str(e)}

    async def get_job_status(self, app_name: str, job_id: str) -> dict[str, Any]:
        """Get job status / Obter status do trabalho."""
        if self.config.fccs_mock_mode:
            return MOCK_JOB_STATUS.get(
                job_id,
                {"jobId": job_id, "status": "Unknown", "details": "Mock job not found"}
            )

        response = await self._client.get(
            f"/{app_name}/jobs/{job_id}{self._get_query_params()}"
        )
        response.raise_for_status()
        return response.json()

    async def run_business_rule(
        self,
        app_name: str,
        rule_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Run business rule / Executar regra de negocio."""
        if self.config.fccs_mock_mode:
            return {**MOCK_RULE_RESULT, "jobName": rule_name}

        payload = {
            "jobType": "Rules",
            "jobName": rule_name,
            "parameters": parameters or {}
        }
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def run_data_rule(
        self,
        app_name: str,
        rule_name: str,
        start_period: str,
        end_period: str,
        import_mode: str = "REPLACE",
        export_mode: str = "STORE_DATA"
    ) -> dict[str, Any]:
        """Run data rule / Executar regra de dados."""
        if self.config.fccs_mock_mode:
            return {**MOCK_DATA_RULE_RESULT, "jobName": rule_name}

        payload = {
            "jobType": "DATARULE",
            "jobName": rule_name,
            "parameters": {
                "startPeriod": start_period,
                "endPeriod": end_period,
                "importMode": import_mode,
                "exportMode": export_mode
            }
        }
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # ========== Dimension Methods ==========

    async def get_dimensions(self, app_name: str) -> dict[str, Any]:
        """Get dimensions / Obter dimensoes."""
        if self.config.fccs_mock_mode:
            return MOCK_DIMENSIONS

        # Try multiple endpoints
        endpoints = [
            f"/{app_name}/dimensions{self._get_query_params()}",
            f"/{app_name}/dimensions",
            f"/{app_name}/metadata/dimensions{self._get_query_params()}",
            f"/{app_name}/metadata/dimensions",
        ]

        for endpoint in endpoints:
            try:
                response = await self._client.get(endpoint)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                continue

        # Fallback to standard FCCS dimensions
        return {
            "items": [
                {"name": "Years", "type": "Time"},
                {"name": "Period", "type": "Time"},
                {"name": "Scenario", "type": "Scenario"},
                {"name": "View", "type": "View"},
                {"name": "Entity", "type": "Entity"},
                {"name": "Consolidation", "type": "Consolidation"},
                {"name": "Account", "type": "Account"},
                {"name": "ICP", "type": "ICP"},
                {"name": "Data Source", "type": "Data Source"},
                {"name": "Movement", "type": "Movement"},
                {"name": "Multi-GAAP", "type": "Multi-GAAP"},
            ],
            "note": "Standard FCCS dimensions (endpoint not available)"
        }

    async def get_members(
        self,
        app_name: str,
        dimension_name: str
    ) -> dict[str, Any]:
        """Get dimension members / Obter membros da dimensao."""
        if self.config.fccs_mock_mode:
            return MOCK_MEMBERS

        # First, try to load from local cache
        cached_members = load_members_from_cache(app_name, dimension_name)
        if cached_members is not None:
            return cached_members

        # If not in cache, try API endpoints
        endpoints = [
            f"/{app_name}/dimensions/{dimension_name}/members{self._get_query_params()}",
            f"/{app_name}/dimensions/{dimension_name}/members",
            f"/{app_name}/metadata/dimensions/{dimension_name}/members{self._get_query_params()}",
            f"/{app_name}/metadata/dimensions/{dimension_name}/members",
            f"/{app_name}/dimensions/{dimension_name}{self._get_query_params()}",
            f"/{app_name}/dimensions/{dimension_name}",
        ]

        for endpoint in endpoints:
            try:
                response = await self._client.get(endpoint)
                if response.status_code == 200:
                    members = response.json()
                    # Save to cache for future use
                    save_members_to_cache(app_name, dimension_name, members)
                    return members
            except Exception:
                continue

        raise ValueError(f"Could not retrieve members for dimension: {dimension_name}")

    async def get_dimension_hierarchy(
        self,
        app_name: str,
        dimension_name: str,
        member_name: Optional[str] = None,
        depth: int = 5,
        include_metadata: bool = False
    ) -> dict[str, Any]:
        """Get dimension hierarchy / Obter hierarquia da dimensao."""
        members_response = await self.get_members(app_name, dimension_name)

        # Extract member items
        member_items = (
            members_response.get("items")
            or members_response.get("members")
            or (members_response if isinstance(members_response, list) else [])
        )

        if not member_items:
            return {
                "dimension": dimension_name,
                "requestedMember": member_name,
                "depth": depth,
                "hierarchy": [],
                "note": "No members returned for this dimension."
            }

        # Build hierarchy tree
        node_map: dict[str, dict] = {}

        for member in member_items:
            name = member.get("memberName") or member.get("name") or member.get("alias")
            if not name or name in node_map:
                continue

            parent_name = (
                member.get("parentName")
                or member.get("parent")
                or member.get("parent_member_name")
            )

            node_map[name] = {
                "node": {
                    "name": name,
                    "description": member.get("description") or member.get("alias"),
                    **({"metadata": member} if include_metadata else {}),
                    "children": [],
                },
                "parentName": parent_name,
            }

        # Link children to parents
        root_nodes = []
        for name, entry in node_map.items():
            parent = entry["parentName"]
            if parent and parent in node_map:
                node_map[parent]["node"]["children"].append(entry["node"])
            else:
                root_nodes.append(entry["node"])

        # Prune to requested depth
        def prune_node(node: dict, remaining_depth: int) -> dict:
            pruned = {"name": node["name"]}
            if node.get("description"):
                pruned["description"] = node["description"]
            if include_metadata and node.get("metadata"):
                pruned["metadata"] = node["metadata"]

            if remaining_depth > 0 and node.get("children"):
                pruned["children"] = [
                    prune_node(child, remaining_depth - 1)
                    for child in node["children"]
                ]
            else:
                pruned["children"] = []
                if node.get("children"):
                    pruned["truncatedChildren"] = len(node["children"])

            return pruned

        # Find target nodes
        if member_name:
            target = node_map.get(member_name)
            if not target:
                # Case-insensitive search
                for key, entry in node_map.items():
                    if key.lower() == member_name.lower():
                        target = entry
                        break
            if not target:
                raise ValueError(f"Member '{member_name}' not found in dimension '{dimension_name}'")
            targets = [target["node"]]
        else:
            targets = root_nodes

        return {
            "dimension": dimension_name,
            "requestedMember": member_name,
            "depth": depth,
            "totalMembers": len(member_items),
            "hierarchy": [prune_node(node, depth) for node in targets],
        }

    # ========== Journal Methods ==========

    async def get_journals(
        self,
        app_name: str,
        filters: Optional[dict[str, str]] = None,
        offset: int = 0,
        limit: int = 100
    ) -> dict[str, Any]:
        """Get journals / Obter lancamentos."""
        if self.config.fccs_mock_mode:
            return {"items": [], "offset": offset, "limit": limit, "count": 0}

        # Build query parameters
        params = {"offset": offset, "limit": limit}
        
        if filters:
            # Build the q parameter as a JSON-like string
            filter_parts = []
            for key in ["scenario", "year", "period", "status", "consolidation", "view", "entity", "group", "label", "description"]:
                if key in filters:
                    filter_parts.append(f'"{key}":"{filters[key]}"')
            if filter_parts:
                # Use proper JSON format for the q parameter
                params["q"] = "{" + ",".join(filter_parts) + "}"

        # Use httpx params to handle URL encoding automatically
        response = await self._client.get(
            f"/{app_name}/journals",
            params=params
        )

        if response.status_code == 200:
            data = response.json()
            if not data.get("items"):
                data["message"] = "No journals currently exist in the system."
            return data

        # Return error details if not 200
        return {
            "items": [],
            "offset": offset,
            "limit": limit,
            "count": 0,
            "error": f"HTTP {response.status_code}",
            "detail": response.text[:500] if response.text else "No response body"
        }

    async def get_journal_details(
        self,
        app_name: str,
        journal_label: str,
        filters: Optional[dict[str, str]] = None,
        line_items: bool = True
    ) -> dict[str, Any]:
        """Get journal details / Obter detalhes do lancamento."""
        if self.config.fccs_mock_mode:
            return {"journalLabel": journal_label, "lineItems": []}

        query_parts = []
        if filters:
            filter_parts = []
            for key in ["scenario", "year", "period"]:
                if key in filters:
                    filter_parts.append(f'"{key}":"{filters[key]}"')
            if filter_parts:
                query_parts.append(f"q={{{','.join(filter_parts)}}}")

        query_parts.append(f"lineItems={str(line_items).lower()}")
        query = "?" + "&".join(query_parts)

        response = await self._client.get(
            f"/{app_name}/journals/{quote(journal_label)}{query}{self._get_query_params(True)}"
        )
        response.raise_for_status()
        return response.json()

    async def perform_journal_action(
        self,
        app_name: str,
        journal_label: str,
        action: str,
        scenario: str,
        year: str,
        period: str,
        consolidation: str = "FCCS_Entity Input",
        comment: Optional[str] = None
    ) -> dict[str, Any]:
        """Perform journal action (SUBMIT, APPROVE, REJECT, POST, UNPOST) / Executar acao no lancamento.
        
        Based on Oracle FCCS REST API documentation:
        POST /HyperionPlanning/rest/{api_version}/applications/{application}/journals/{journal_label}/actions
        
        Args:
            app_name: Application name (e.g., 'Consol')
            journal_label: The journal label (will be URL encoded)
            action: Action to perform - SUBMIT, APPROVE, REJECT, POST, UNPOST
            scenario: Scenario name (required, e.g., 'Actual')
            year: Year (required, e.g., 'FY25')
            period: Period (required, e.g., 'Mar')
            consolidation: Consolidation member (default: 'FCCS_Entity Input')
            comment: Optional comment for the action
            
        Returns:
            dict: Action result with status
        """
        if self.config.fccs_mock_mode:
            return {
                "journalLabel": journal_label,
                "action": action.upper(),
                "status": "Success",
                "message": f"Journal action '{action}' completed successfully (mock mode)"
            }

        # Build the q parameter as required by FCCS REST API
        # Format: q={"scenario":"Actual","year":"FY25","period":"Mar","consolidation":"FCCS_Entity Input"}
        import json
        q_filter = json.dumps({
            "scenario": scenario,
            "year": year,
            "period": period,
            "consolidation": consolidation
        })
        
        # Build query parameters - action may need to be in query string
        params = {
            "q": q_filter,
            "action": action.upper()  # Try action in query string
        }
        
        # Add admin mode if needed
        if self.admin_mode:
            params["adminMode"] = "true"
        
        # Try with empty body first (some FCCS APIs don't accept body)
        # URL encode the journal label (spaces become %20, etc.)
        encoded_label = quote(journal_label, safe='')
        
        try:
            # First attempt: action in query string, no body
            response = await self._client.post(
                f"/{app_name}/journals/{encoded_label}/actions",
                params=params,
                json={}  # Empty body
            )
            
            if response.status_code == 200:
                return response.json()
            
            # If that fails, try with action in body
            if response.status_code == 400:
                params_without_action = {"q": q_filter}
                if self.admin_mode:
                    params_without_action["adminMode"] = "true"
                    
                payload = {"action": action.upper()}
                if comment:
                    payload["comment"] = comment
                    
                response = await self._client.post(
                    f"/{app_name}/journals/{encoded_label}/actions",
                    params=params_without_action,
                    json=payload
                )
                
                if response.status_code == 200:
                    return response.json()
            else:
                # Return detailed error information
                return {
                    "status": "error",
                    "httpStatus": response.status_code,
                    "message": f"Journal action failed with HTTP {response.status_code}",
                    "detail": response.text[:1000] if response.text else "No response body",
                    "request": {
                        "journalLabel": journal_label,
                        "action": action.upper(),
                        "scenario": scenario,
                        "year": year,
                        "period": period,
                        "consolidation": consolidation
                    }
                }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "request": {
                    "journalLabel": journal_label,
                    "action": action.upper(),
                    "scenario": scenario,
                    "year": year,
                    "period": period,
                    "consolidation": consolidation
                }
            }

    async def update_journal_period(
        self,
        app_name: str,
        journal_label: str,
        new_period: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Update journal period / Atualizar periodo do lancamento."""
        if self.config.fccs_mock_mode:
            return {"journalLabel": journal_label, "newPeriod": new_period, "status": "Updated"}

        payload = {"period": new_period, **(parameters or {})}
        response = await self._client.put(
            f"/{app_name}/journals/{quote(journal_label)}{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def export_journals(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Export journals / Exportar lancamentos."""
        if self.config.fccs_mock_mode:
            return {"jobId": "601", "status": "Submitted", "jobType": "ExportJournals"}

        payload = {"jobType": "EXPORTJOURNALS", **(parameters or {})}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def import_journals(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Import journals / Importar lancamentos."""
        if self.config.fccs_mock_mode:
            return {"jobId": "602", "status": "Submitted", "jobType": "ImportJournals"}

        payload = {"jobType": "IMPORTJOURNALS", **(parameters or {})}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # ========== Data Methods ==========

    async def export_data_slice(
        self,
        app_name: str,
        cube_name: str,
        grid_definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Export data slice / Exportar fatia de dados."""
        if self.config.fccs_mock_mode:
            return MOCK_DATA_SLICE

        db_name = cube_name or "Consol"
        payload = {"gridDefinition": grid_definition}

        response = await self._client.post(
            f"/{app_name}/plantypes/{db_name}/exportdataslice{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def import_data_slice(
        self,
        app_name: str,
        cube_name: str,
        data_grid: dict[str, Any],
        aggregation_option: str = "REPLACE"
    ) -> dict[str, Any]:
        """Import data slice - write data to cells / Importar fatia de dados.
        
        This is the write counterpart to export_data_slice.
        
        Args:
            app_name: Application name.
            cube_name: Cube/plan type name (e.g., 'Consol').
            data_grid: Grid definition with POV, columns, rows INCLUDING data values.
                rows format: [{"members": [["Account1"]], "data": [100, 200, ...]}, ...]
            aggregation_option: How to handle existing data:
                - 'REPLACE': Overwrite existing values
                - 'ADD': Add to existing values
                - 'SUBTRACT': Subtract from existing values
                
        Returns:
            dict: Import result with status and any validation errors.
        """
        if self.config.fccs_mock_mode:
            return {
                "status": "success",
                "numAcceptedCells": len(data_grid.get("rows", [])),
                "numRejectedCells": 0,
                "message": "Data imported successfully (mock mode)"
            }

        db_name = cube_name or "Consol"
        
        # Build payload according to Oracle EPM REST API spec
        payload = {
            "aggregateData": aggregation_option == "ADD",
            "dateFormat": "MM-DD-YYYY",
            "gridDefinition": data_grid
        }
        
        # For SUBTRACT, we need to negate values (EPM doesn't have native subtract)
        if aggregation_option == "SUBTRACT":
            payload["aggregateData"] = True
            # Negate all data values
            for row in payload["gridDefinition"].get("rows", []):
                if "data" in row:
                    row["data"] = [-v if isinstance(v, (int, float)) else v for v in row["data"]]
        
        try:
            response = await self._client.post(
                f"/{app_name}/plantypes/{db_name}/importdataslice{self._get_query_params()}",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Return structured error
            return {
                "status": "error",
                "error": str(e),
                "message": f"Failed to import data: {str(e)}",
                "payload_sent": {
                    "cube": db_name,
                    "row_count": len(data_grid.get("rows", [])),
                    "aggregation_option": aggregation_option
                }
            }

    async def copy_data(
        self,
        app_name: str,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Copy data / Copiar dados."""
        if self.config.fccs_mock_mode:
            return {"jobId": "401", "status": "Submitted", "jobType": "CopyData"}

        payload = {"jobType": "COPYDATA", **parameters}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def clear_data(
        self,
        app_name: str,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Clear data / Limpar dados."""
        if self.config.fccs_mock_mode:
            return {"jobId": "402", "status": "Submitted", "jobType": "ClearData"}

        payload = {"jobType": "CLEARDATA", **parameters}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # ========== Consolidation Methods ==========

    async def export_consolidation_rulesets(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Export consolidation rulesets / Exportar regras de consolidacao."""
        if self.config.fccs_mock_mode:
            return {"jobId": "301", "status": "Submitted", "jobType": "ExportRulesets"}

        payload = parameters or {}
        if not payload.get("ruleNames") and not payload.get("rulesetNames"):
            return {
                "status": "Parameter Required",
                "message": "Consolidation ruleset export requires specific rule names.",
                "suggestion": "Provide 'ruleNames' or 'rulesetNames' in parameters."
            }

        response = await self._client.post(
            f"/{app_name}/exportConfigConsolRules{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def import_consolidation_rulesets(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Import consolidation rulesets / Importar regras de consolidacao."""
        if self.config.fccs_mock_mode:
            return {"jobId": "302", "status": "Submitted", "jobType": "ImportRulesets"}

        response = await self._client.post(
            f"/{app_name}/importConfigConsolRules{self._get_query_params()}",
            json=parameters or {}
        )
        response.raise_for_status()
        return response.json()

    async def validate_metadata(
        self,
        app_name: str,
        log_file_name: Optional[str] = None
    ) -> dict[str, Any]:
        """Validate metadata / Validar metadados."""
        if self.config.fccs_mock_mode:
            return {"status": "Completed", "validationResults": []}

        query = f"?logFileName={quote(log_file_name)}" if log_file_name else ""
        response = await self._client.post(
            f"/{app_name}/validatemetadata{query}{self._get_query_params(bool(query))}",
            json={}
        )
        response.raise_for_status()
        return response.json()

    async def generate_intercompany_matching_report(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Generate intercompany matching report / Gerar relatorio ICP."""
        if self.config.fccs_mock_mode:
            return {"jobId": "501", "status": "Submitted", "jobType": "IntercompanyMatching"}

        payload = {"jobType": "INTERCOMPANYMATCHING", **(parameters or {})}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # ========== Report Methods ==========

    async def generate_report(
        self,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate report / Gerar relatorio."""
        if self.config.fccs_mock_mode:
            return {
                "type": parameters.get("module", "FCM"),
                "status": -1 if parameters.get("runAsync") else 0,
                "details": "In Process" if parameters.get("runAsync") else f"{parameters.get('reportName')}.pdf",
                "links": []
            }

        payload = {
            "groupName": parameters.get("groupName"),
            "reportName": parameters.get("reportName"),
            "format": parameters.get("format", "PDF"),
            "module": parameters.get("module", "FCM"),
            "runAsync": parameters.get("runAsync", False),
        }
        if parameters.get("generatedReportFileName"):
            payload["generatedReportFileName"] = parameters["generatedReportFileName"]
        if parameters.get("parameters"):
            payload["parameters"] = parameters["parameters"]
        if parameters.get("emails"):
            payload["emails"] = parameters["emails"]

        response = await self._fcm_client.post("/report", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_report_job_status(
        self,
        job_id: str,
        report_type: str = "FCCS"
    ) -> dict[str, Any]:
        """Get report job status / Obter status do trabalho de relatorio."""
        if self.config.fccs_mock_mode:
            return {"jobId": job_id, "status": "Completed", "details": "Report generation completed"}

        response = await self._fcm_client.get(f"/report/job/{report_type}/{job_id}")
        response.raise_for_status()
        return response.json()

    # ========== Supplemental Data Methods ==========

    async def import_supplementation_data(
        self,
        app_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Import supplementation data / Importar dados suplementares."""
        if self.config.fccs_mock_mode:
            return {"jobId": "701", "status": "Submitted", "jobType": "ImportSupplementationData"}

        payload = {"jobType": "IMPORTSUPPLEMENTATIONDATA", **(parameters or {})}
        response = await self._client.post(
            f"/{app_name}/jobs{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def deploy_form_template(
        self,
        app_name: str,
        template_name: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Deploy form template / Implantar modelo de formulario."""
        if self.config.fccs_mock_mode:
            return {"templateName": template_name, "status": "Deployed"}

        payload = {"templateName": template_name, **(parameters or {})}
        response = await self._client.post(
            f"/{app_name}/formtemplates/{quote(template_name)}/actions/deploy{self._get_query_params()}",
            json=payload
        )
        response.raise_for_status()
        return response.json()
