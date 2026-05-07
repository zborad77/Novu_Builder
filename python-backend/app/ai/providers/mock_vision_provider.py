class MockVisionProvider:
    key = "mock"

    @staticmethod
    def _extract_rehearsal_failure_mode(project: dict) -> tuple[str | None, int]:
        description = str(project.get("description") or "")
        address = str(project.get("address_label") or "")
        combined = f"{description} {address}"
        lowered = combined.lower()

        if "[rehearsal:fail-always]" in lowered:
            return "always", 0

        marker = "[rehearsal:fail-until-attempt="
        if marker in lowered:
            start = lowered.index(marker) + len(marker)
            end = lowered.find("]", start)
            if end > start:
                try:
                    return "until_attempt", max(1, int(lowered[start:end]))
                except ValueError:
                    return "until_attempt", 1

        return None, 0

    @staticmethod
    def build_mock_mask() -> list[dict[str, float]]:
        return [
            {"x": 0.12, "y": 0.16},
            {"x": 0.84, "y": 0.17},
            {"x": 0.88, "y": 0.86},
            {"x": 0.14, "y": 0.87},
        ]

    async def analyze_project(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None = None,
    ) -> dict:
        failure_mode, failure_attempt_limit = self._extract_rehearsal_failure_mode(project)
        attempt_count = int(project.get("attemptCount") or 0)
        if failure_mode == "always":
            raise RuntimeError("Mock rehearsal injected persistent failure.")
        if failure_mode == "until_attempt" and attempt_count <= failure_attempt_limit:
            raise RuntimeError(
                f"Mock rehearsal injected retryable failure on attempt {attempt_count} "
                f"(limit={failure_attempt_limit})."
            )

        description = str(project.get("description") or "").lower()
        address = str(project.get("address_label") or "").lower()
        normalized_text = f"{description} {address}"
        photo_count = len(photos) or 1
        gps_photo_count = sum(1 for photo in photos if photo.get("hasGps"))
        portrait_count = sum(1 for photo in photos if photo.get("orientation") == "portrait")
        landscape_count = sum(1 for photo in photos if photo.get("orientation") == "landscape")
        has_closeups = any(
            photo.get("orientation") == "portrait"
            or (isinstance(photo.get("width"), int) and photo["width"] < 1200)
            for photo in photos
        )
        has_wide_coverage = landscape_count >= 2 or photo_count >= 3
        is_roof = "strecha" in normalized_text or (analysis_config or {}).get("workTypeCode") == "roof-repair"
        is_cleaning = any(term in normalized_text for term in ("cisteni", "ocisteni", "myti"))
        analysis_profile = ((analysis_config or {}).get("analysisProfile") or {})
        extraction_rules = analysis_profile.get("extractionRules") or []
        default_unit = (analysis_config or {}).get("defaultUnit") or "m2"

        object_type = "roof" if is_roof else "facade"
        recommended_scope = (
            "cleaning"
            if is_cleaning
            else "local_repair"
            if has_closeups
            else "full_reconstruction"
            if has_wide_coverage
            else "local_repair"
        )

        base_area = 52 if is_roof else 28
        photo_area_boost = photo_count * (6.5 if is_roof else 7.5)
        orientation_boost = landscape_count * 1.4 + portrait_count * 0.9
        gps_boost = gps_photo_count * 0.6
        estimated_area = round(base_area + photo_area_boost + orientation_boost + gps_boost, 1)
        area_confidence = round(
            min(0.52 + photo_count * 0.05 + gps_photo_count * 0.03 + landscape_count * 0.02, 0.93), 2
        )

        if is_cleaning:
            materials = [
                {
                    "name": "Penetrace",
                    "unit": "l",
                    "quantity": round(estimated_area * 0.22, 1),
                    "unitPrice": 95.0,
                    "totalPrice": round(estimated_area * 0.22 * 95.0, 2),
                },
                {
                    "name": "Fasadni nater",
                    "unit": "kg",
                    "quantity": round(estimated_area * 0.28, 1),
                    "unitPrice": 185.0,
                    "totalPrice": round(estimated_area * 0.28 * 185.0, 2),
                },
            ]
            workflow_steps = [
                {
                    "step": 1,
                    "name": "Vizualni kontrola povrchu",
                    "description": "Posouzeni stavu povrchu, zdokumentovani poskozeni a znecisteni.",
                    "estimatedHours": 1,
                },
                {
                    "step": 2,
                    "name": "Ocisteni podkladu",
                    "description": "Tlakove cisteni fasady, odstraneni mechu, riz a prachu.",
                    "estimatedHours": round(estimated_area * 0.08, 1),
                },
                {
                    "step": 3,
                    "name": "Aplikace cistici a ochranne vrstvy",
                    "description": "Penetrace a finalni fasadni nater v jedne vrstve.",
                    "estimatedHours": round(estimated_area * 0.06, 1),
                },
            ]
        else:
            materials = [
                {
                    "name": "Penetrace",
                    "unit": "l",
                    "quantity": round(estimated_area * 0.35, 1),
                    "unitPrice": 95.0,
                    "totalPrice": round(estimated_area * 0.35 * 95.0, 2),
                },
                {
                    "name": "Opravna smes",
                    "unit": "kg",
                    "quantity": round(estimated_area * 2.8, 1),
                    "unitPrice": 42.0,
                    "totalPrice": round(estimated_area * 2.8 * 42.0, 2),
                },
            ]
            if not is_roof:
                materials.append({
                    "name": "Fasadni nater",
                    "unit": "kg",
                    "quantity": round(estimated_area * 0.45, 1),
                    "unitPrice": 185.0,
                    "totalPrice": round(estimated_area * 0.45 * 185.0, 2),
                })
            prep_hours = round(estimated_area * 0.05, 1)
            repair_hours = round(estimated_area * 0.18, 1)
            coat_hours = round(estimated_area * 0.08, 1)
            workflow_steps = [
                {
                    "step": 1,
                    "name": "Vizualni kontrola a dokumentace",
                    "description": "Posouzeni rozsahu poskozeni, zakresleni opravnych zon.",
                    "estimatedHours": 1,
                },
                {
                    "step": 2,
                    "name": "Priprava podkladu",
                    "description": "Ocisteni, odmasteni, broušeni a penetrace povrchu.",
                    "estimatedHours": prep_hours,
                },
                {
                    "step": 3,
                    "name": "Lokalni oprava poskozeni",
                    "description": "Vyplneni trhlin a dutin opravnou smesi, vyrovnani plochy.",
                    "estimatedHours": repair_hours,
                },
                {
                    "step": 4,
                    "name": "Aplikace finalni vrstvy",
                    "description": "Finalni nater nebo omitka dle specifikace.",
                    "estimatedHours": coat_hours,
                },
            ]

        total_hours = sum(step["estimatedHours"] for step in workflow_steps)  # type: ignore[misc]
        estimated_total_days = round(total_hours / 8, 1)
        catalog_attributes: dict[str, dict] = {}
        for rule in extraction_rules:
            attribute_code = rule.get("attributeCode")
            data_type = rule.get("dataType")
            if not attribute_code or not data_type:
                continue
            if data_type == "number":
                base_value = estimated_area
                if attribute_code.endswith("deg"):
                    base_value = 18 if is_roof else 2
                elif attribute_code.endswith("count") or attribute_code == "quantity":
                    base_value = max(1, min(photo_count, 4))
                catalog_attributes[attribute_code] = {
                    "value": round(base_value, 1),
                    "confidence": area_confidence,
                    "sourceObjectCode": rule.get("sourceObjectCode"),
                }
            elif data_type == "option":
                allowed_option_codes = rule.get("allowedOptionCodes") or []
                preferred_option = allowed_option_codes[0] if allowed_option_codes else "moderate"
                catalog_attributes[attribute_code] = {
                    "value": preferred_option,
                    "confidence": max(area_confidence - 0.08, 0.45),
                    "sourceObjectCode": rule.get("sourceObjectCode"),
                }
            elif data_type == "boolean":
                catalog_attributes[attribute_code] = {
                    "value": True,
                    "confidence": max(area_confidence - 0.05, 0.5),
                    "sourceObjectCode": rule.get("sourceObjectCode"),
                }
            else:
                catalog_attributes[attribute_code] = {
                    "value": f"Mock extraction for {attribute_code}",
                    "confidence": max(area_confidence - 0.12, 0.42),
                    "sourceObjectCode": rule.get("sourceObjectCode"),
                }

        return {
            "providerKey": "mock",
            "jobType": "vision_mock",
            "objectType": object_type,
            "surfaceCondition": "requires_attention",
            "recommendedScope": recommended_scope,
            "estimatedQuantity": estimated_area,
            "estimatedUnit": default_unit,
            "estimatedAreaSqm": estimated_area,
            "areaConfidence": area_confidence,
            "maskPolygon": self.build_mock_mask(),
            "materials": materials,
            "workflowSteps": workflow_steps,
            "estimatedTotalDays": estimated_total_days,
            "laborHoursTotal": total_hours,
            "catalogAttributes": catalog_attributes,
            "analysisProfileCode": analysis_profile.get("code"),
            "analysisProfileVersion": analysis_profile.get("version"),
            "resolvedWorkTypeCode": (analysis_config or {}).get("workTypeCode"),
            "modelName": "mock-vision",
            "modelVersion": "0.3",
        }
