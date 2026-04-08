from __future__ import annotations

from dataclasses import asdict

from app.core.config.tor_config_manager import TorConfigManager
from app.core.constants import SUPPORTED_TORRC_OPTIONS
from app.core.detection.environment_detector import EnvironmentDetector
from app.core.diagnostics.diagnostics_runner import DiagnosticsRunner
from app.core.logs.log_reader import LogReader
from app.core.service.tor_service_manager import TorServiceManager
from app.db.repository import DatabaseRepository
from app.schemas.config import ConfigReadResponse, ConfigValidationResponse
from app.schemas.diagnostics import DiagnosticItem, DiagnosticsResponse
from app.schemas.environment import EnvironmentInfo
from app.schemas.logs import LogResponse
from app.schemas.onion import OnionServiceCreateResponse, OnionServiceDeleteResponse, OnionServiceItem, OnionServiceListResponse
from app.schemas.service import ServiceActionResponse, ServiceStatusResponse


class TunatorService:
    def __init__(self, detector: EnvironmentDetector, repository: DatabaseRepository):
        self.detector = detector
        self.repository = repository
        self.environment = self.detector.detect()
        self.config_manager = TorConfigManager(self.environment.torrc_path)
        self.service_manager = TorServiceManager(self.environment)
        self.log_reader = LogReader(self.environment.log_path)
        self.diagnostics_runner = DiagnosticsRunner(self.environment, self.detector, self.service_manager, self.config_manager)

    @classmethod
    def bootstrap(cls) -> 'TunatorService':
        return cls(detector=EnvironmentDetector(), repository=DatabaseRepository.from_env())

    def _refresh_environment(self) -> None:
        self.environment = self.detector.detect()
        self.config_manager = TorConfigManager(self.environment.torrc_path)
        self.service_manager.env = self.environment
        self.log_reader = LogReader(self.environment.log_path)
        self.diagnostics_runner = DiagnosticsRunner(self.environment, self.detector, self.service_manager, self.config_manager)

    def get_environment(self) -> EnvironmentInfo:
        self._refresh_environment()
        return EnvironmentInfo(**asdict(self.environment))

    def get_status(self) -> ServiceStatusResponse:
        self._refresh_environment()
        status = self.service_manager.status()
        return ServiceStatusResponse(**asdict(status))

    def read_config(self) -> ConfigReadResponse:
        self._refresh_environment()
        model = self.config_manager.parse_model()
        onion_items = [OnionServiceItem(**item) for item in model['onion_services']]
        return ConfigReadResponse(
            raw=self.config_manager.read_raw(),
            parsed=self.config_manager.read_parsed(),
            base_options=model['base_options'],
            onion_services=onion_items,
            supported_options=sorted(list(SUPPORTED_TORRC_OPTIONS)),
        )

    def validate_config(self, updates: dict[str, str]) -> ConfigValidationResponse:
        self._refresh_environment()
        result = self.config_manager.validate_updates(updates)
        self.repository.record_config_change(updates, False, result.errors)
        return ConfigValidationResponse(valid=result.valid, errors=result.errors, warnings=result.warnings)

    def apply_config(self, updates: dict[str, str]) -> dict:
        self._refresh_environment()
        validation = self.config_manager.validate_updates(updates)
        if not validation.valid:
            self.repository.record_config_change(updates, False, validation.errors)
            return {'success': False, 'errors': validation.errors, 'warnings': validation.warnings}

        backup_path = self.config_manager.create_backup()
        parsed = self.config_manager.apply_updates(updates)
        self.repository.record_config_change(updates, True, [])
        return {
            'success': True,
            'backup_path': backup_path,
            'parsed': parsed,
            'warnings': validation.warnings,
        }

    def list_onion_services(self) -> OnionServiceListResponse:
        self._refresh_environment()
        items = [OnionServiceItem(**item) for item in self.config_manager.list_onion_services()]
        return OnionServiceListResponse(items=items)

    def create_onion_service(
        self,
        name: str,
        public_port: int,
        target_host: str,
        target_port: int,
        access_password: str | None = None,
    ) -> OnionServiceCreateResponse:
        self._refresh_environment()
        validation = self.config_manager.validate_onion_service(name, public_port, target_host, target_port, access_password)
        if not validation.valid:
            raise ValueError('; '.join(validation.errors))
        backup_path = self.config_manager.create_backup()
        item = self.config_manager.create_onion_service(name, public_port, target_host, target_port, access_password)
        return OnionServiceCreateResponse(
            success=True,
            item=OnionServiceItem(**item),
            backup_path=backup_path,
            warnings=validation.warnings,
        )

    def delete_onion_service(self, name: str) -> OnionServiceDeleteResponse:
        self._refresh_environment()
        backup_path = self.config_manager.create_backup()
        result = self.config_manager.remove_onion_service(name)
        return OnionServiceDeleteResponse(success=True, backup_path=backup_path, **result)

    def read_logs(self, limit: int = 200) -> LogResponse:
        self._refresh_environment()
        return LogResponse(entries=self.log_reader.read_recent(limit=limit))

    def run_diagnostics(self) -> DiagnosticsResponse:
        self._refresh_environment()
        checks = self.diagnostics_runner.run()
        payload = [asdict(item) for item in checks]
        self.repository.record_diagnostics('full', payload)
        return DiagnosticsResponse(checks=[DiagnosticItem(**item) for item in payload])

    def start_service(self) -> ServiceActionResponse:
        self._refresh_environment()
        result = self.service_manager.start()
        return ServiceActionResponse(**asdict(result))

    def stop_service(self) -> ServiceActionResponse:
        self._refresh_environment()
        result = self.service_manager.stop()
        return ServiceActionResponse(**asdict(result))

    def restart_service(self) -> ServiceActionResponse:
        self._refresh_environment()
        result = self.service_manager.restart()
        return ServiceActionResponse(**asdict(result))
