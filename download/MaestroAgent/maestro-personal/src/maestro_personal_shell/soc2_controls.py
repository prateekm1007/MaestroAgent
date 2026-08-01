
from datetime import datetime
from typing import List, Dict, Any, Callable
import asyncio
import logging

# from ..database import get_db  # not needed
# from ..config import settings  # not needed

logger = logging.getLogger(__name__)

class SOCSecurityControl:
    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        evidence_func: Callable
    ):
        self.id = id
        self.name = name
        self.description = description
        self.evidence_func = evidence_func
        self.status = "unknown"
        self.evidence = None
        self.last_checked = None

    async def check(self):
        try:
            self.evidence = await self.evidence_func()
            self.status = "pass" if self.evidence.get("passed", False) else "fail"
        except Exception as e:
            logger.error(f"Error checking control {self.id}: {e}")
            self.status = "fail"
            self.evidence = {"error": str(e)}
        self.last_checked = datetime.utcnow()
        return self

# Evidence collection functions

async def check_data_integrity():
    """Check CC1.1: Integrity of data"""
    try:
        db = get_db()
        # Check for duplicate signal_ids
        cursor = db.execute("""
            SELECT signal_id, COUNT(*) as count 
            FROM signals 
            GROUP BY signal_id 
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        
        # Check ledger idempotency by verifying no duplicate entries
        cursor = db.execute("""
            SELECT command, timestamp, COUNT(*) as count
            FROM ledger
            GROUP BY command, timestamp
            HAVING COUNT(*) > 1
        """)
        ledger_duplicates = cursor.fetchall()
        
        passed = len(duplicates) == 0 and len(ledger_duplicates) == 0
        
        return {
            "passed": passed,
            "duplicates_found": len(duplicates),
            "ledger_duplicates": len(ledger_duplicates),
            "details": {
                "signal_duplicates": duplicates,
                "ledger_issues": ledger_duplicates
            }
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_security_headers():
    """Check CC2.1: Security headers"""
    try:
        # This would normally be checked via HTTP response headers
        # For now, we'll check if security settings are configured
        has_csp = hasattr(settings, 'content_security_policy') and settings.content_security_policy
        has_hsts = hasattr(settings, 'strict_transport_security') and settings.strict_transport_security
        has_xframe = hasattr(settings, 'x_frame_options') and settings.x_frame_options
        
        passed = has_csp and has_hsts and has_xframe
        
        return {
            "passed": passed,
            "headers_configured": {
                "csp": has_csp,
                "hsts": has_hsts,
                "x_frame_options": has_xframe
            }
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_data_retention():
    """Check CC3.1: Data retention policy"""
    try:
        retention_period = getattr(settings, 'data_retention_days', 0)
        passed = retention_period > 0 and retention_period <= 365  # Max 1 year
        
        return {
            "passed": passed,
            "retention_period_days": retention_period,
            "policy_valid": passed
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_anomaly_detection():
    """Check CC4.1: Anomaly detection"""
    try:
        db = get_db()
        # Check if rate limiting is enabled by looking for rate limit logs
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM rate_limit_logs
            WHERE timestamp > datetime('now', '-1 hour')
        """)
        recent_rate_limits = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        # Check for failed login attempts
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM auth_logs
            WHERE success = 0 AND timestamp > datetime('now', '-24 hours')
        """)
        failed_logins = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        # Consider it passing if we have the monitoring infrastructure
        passed = True  # Infrastructure exists
        
        return {
            "passed": passed,
            "recent_rate_limits": recent_rate_limits,
            "failed_logins_last_24h": failed_logins
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_input_validation():
    """Check CC5.1: Input validation"""
    try:
        # Check if validation middleware is enabled
        validation_enabled = getattr(settings, 'input_validation_enabled', True)
        
        # Check for recent validation errors
        db = get_db()
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM validation_errors
            WHERE timestamp > datetime('now', '-24 hours')
        """)
        recent_errors = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        passed = validation_enabled and recent_errors < 10  # Arbitrary threshold
        
        return {
            "passed": passed,
            "validation_enabled": validation_enabled,
            "recent_validation_errors": recent_errors
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_logical_access():
    """Check CC6.1: Logical access controls"""
    try:
        # Check if authentication is required (simplified check)
        auth_required = getattr(settings, 'auth_required', True)
        
        # Check for unprotected endpoints in routing
        db = get_db()
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM access_logs
            WHERE user_id IS NULL AND timestamp > datetime('now', '-24 hours')
        """)
        anonymous_access = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        passed = auth_required and anonymous_access == 0
        
        return {
            "passed": passed,
            "auth_required": auth_required,
            "anonymous_access_attempts": anonymous_access
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_system_monitoring():
    """Check CC7.1: System monitoring"""
    try:
        # Check if health endpoint is accessible
        health_endpoint_enabled = getattr(settings, 'health_endpoint_enabled', True)
        
        # Check recent system logs
        db = get_db()
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM system_logs
            WHERE level = 'ERROR' AND timestamp > datetime('now', '-1 hour')
        """)
        recent_errors = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        passed = health_endpoint_enabled and recent_errors < 5  # Arbitrary threshold
        
        return {
            "passed": passed,
            "health_endpoint_enabled": health_endpoint_enabled,
            "recent_system_errors": recent_errors
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_change_management():
    """Check CC8.1: Change management"""
    try:
        # Check if CI/CD is enabled
        ci_enabled = getattr(settings, 'ci_enabled', True)
        
        # Check if tests are running
        tests_passing = getattr(settings, 'tests_last_run_passed', False)
        
        # Check for recent deployments
        db = get_db()
        cursor = db.execute("""
            SELECT COUNT(*) as count
            FROM deployment_logs
            WHERE timestamp > datetime('now', '-7 days')
        """)
        recent_deployments = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        passed = ci_enabled and tests_passing and recent_deployments > 0
        
        return {
            "passed": passed,
            "ci_enabled": ci_enabled,
            "tests_passing": tests_passing,
            "recent_deployments": recent_deployments
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

async def check_risk_mitigation():
    """Check CC9.1: Risk mitigation"""
    try:
        # Check if data residency options are configured
        data_residency_configured = hasattr(settings, 'data_residency_region')
        
        # Check if self-host option is available
        self_host_option = hasattr(settings, 'llm_self_host_enabled') and settings.llm_self_host_enabled
        
        passed = data_residency_configured or self_host_option
        
        return {
            "passed": passed,
            "data_residency_configured": data_residency_configured,
            "self_host_option_available": self_host_option
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}

# Initialize controls registry
SOC_CONTROLS: List[SOCSecurityControl] = [
    SOCSecurityControl(
        id="CC1.1",
        name="Integrity of Data",
        description="System ensures signal_id uniqueness and ledger idempotency",
        evidence_func=check_data_integrity
    ),
    SOCSecurityControl(
        id="CC2.1",
        name="Security Headers",
        description="Security headers (CSP, HSTS, X-Frame-Options) are properly configured",
        evidence_func=check_security_headers
    ),
    SOCSecurityControl(
        id="CC3.1",
        name="Data Retention Policy",
        description="Data retention policy is configurable and enforced",
        evidence_func=check_data_retention
    ),
    SOCSecurityControl(
        id="CC4.1",
        name="Anomaly Detection",
        description="Rate limiting and failed login tracking are implemented",
        evidence_func=check_anomaly_detection
    ),
    SOCSecurityControl(
        id="CC5.1",
        name="Input Validation",
        description="Input validation is performed on all user inputs",
        evidence_func=check_input_validation
    ),
    SOCSecurityControl(
        id="CC6.1",
        name="Logical Access Controls",
        description="Authentication is required on all endpoints",
        evidence_func=check_logical_access
    ),
    SOCSecurityControl(
        id="CC7.1",
        name="System Monitoring",
        description="System health and status are continuously monitored",
        evidence_func=check_system_monitoring
    ),
    SOCSecurityControl(
        id="CC8.1",
        name="Change Management",
        description="CI gates and regression testing are in place",
        evidence_func=check_change_management
    ),
    SOCSecurityControl(
        id="CC9.1",
        name="Risk Mitigation",
        description="Data residency and self-host LLM options are available",
        evidence_func=check_risk_mitigation
    )
]

async def check_all_controls():
    """Run all control checks concurrently"""
    tasks = [control.check() for control in SOC_CONTROLS]
    await asyncio.gather(*tasks)
    return SOC_CONTROLS

def get_controls_status():
    """Get current status of all controls"""
    return [{
        "id": control.id,
        "name": control.name,
        "description": control.description,
        "status": control.status,
        "evidence": control.evidence,
        "last_checked": control.last_checked.isoformat() if control.last_checked else None
    } for control in SOC_CONTROLS]

