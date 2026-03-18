class MockVisionProvider:
    key = "mock"

    @staticmethod
    def build_mock_mask() -> list[dict[str, float]]:
        return [
            {"x": 0.12, "y": 0.16},
            {"x": 0.84, "y": 0.17},
            {"x": 0.88, "y": 0.86},
            {"x": 0.14, "y": 0.87},
        ]

    async def analyze_project(self, *, project: dict, photos: list[dict]) -> dict:
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
        is_roof = "strecha" in description or "strecha" in address
        is_cleaning = any(term in normalized_text for term in ("cisteni", "ocisteni", "myti"))

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
        area_confidence = round(min(0.52 + photo_count * 0.05 + gps_photo_count * 0.03 + landscape_count * 0.02, 0.93), 2)

        materials = (
            [
                {"name": "Penetrace", "unit": "l", "quantity": round(estimated_area * 0.22)},
                {"name": "Fasadni nater", "unit": "kg", "quantity": round(estimated_area * 0.28)},
            ]
            if is_cleaning
            else [
                {"name": "Penetrace", "unit": "l", "quantity": round(estimated_area * 0.35)},
                {"name": "Opravna smes", "unit": "kg", "quantity": round(estimated_area * 2.8)},
            ]
        )

        workflow = [
            "Vizualni kontrola povrchu",
            "Ocisteni a priprava podkladu",
            "Aplikace cistici a ochranne vrstvy" if is_cleaning else "Lokalni oprava a finalni vrstva",
        ]

        return {
            "providerKey": "mock",
            "jobType": "vision_mock",
            "objectType": object_type,
            "surfaceCondition": "requires_attention",
            "recommendedScope": recommended_scope,
            "estimatedAreaSqm": estimated_area,
            "areaConfidence": area_confidence,
            "maskPolygon": self.build_mock_mask(),
            "materials": materials,
            "workflow": workflow,
            "modelName": "mock-vision",
            "modelVersion": "0.2",
        }
