"""Python script generator for custom FCCS reports."""

from pathlib import Path
from typing import Any, Optional


def generate_report_script(
    script_name: str,
    report_type: str = "HTML",
    description: str = "Custom FCCS report",
    accounts: Optional[list[str]] = None,
    entities: Optional[list[str]] = None,
    periods: Optional[list[str]] = None,
    years: Optional[list[str]] = None,
    scenarios: Optional[list[str]] = None
) -> dict[str, Any]:
    """Generate a Python script template for custom FCCS reporting.
    
    Args:
        script_name: Name of the script file (without .py extension).
        report_type: Type of report - HTML, PDF, or CSV (default: HTML).
        description: Description of what the report does.
        accounts: List of account names to query.
        entities: List of entity names to query.
        periods: List of periods to query (e.g., ['Jan', 'Feb', 'Dec']).
        years: List of years to query (e.g., ['FY24', 'FY25']).
        scenarios: List of scenarios to query (e.g., ['Actual', 'Budget']).
    
    Returns:
        dict: Path to generated script and summary.
    """
    try:
        # Ensure script name ends with .py
        if not script_name.endswith('.py'):
            script_name = f"{script_name}.py"
        
        # Default values
        accounts = accounts or ["FCCS_Net Income"]
        entities = entities or ["FCCS_Total Geography"]
        periods = periods or ["Dec"]
        years = years or ["FY25"]
        scenarios = scenarios or ["Actual"]
        
        script_base_name = script_name.replace('.py', '')
        
        # Build script content using string concatenation to avoid f-string nesting issues
        script_lines = [
            f'"""Generate {description}."""',
            '',
            'import asyncio',
            'import sys',
            'from pathlib import Path',
            'from datetime import datetime',
            'from typing import Optional, Dict, List',
            '',
            '# Add parent directory to path',
            'sys.path.insert(0, str(Path(__file__).parent.parent))',
            '',
            'from fccs_agent.config import load_config',
            'from fccs_agent.agent import initialize_agent, close_agent',
            'from fccs_agent.tools.data import smart_retrieve',
            'from fccs_agent.utils.cache import load_members_from_cache',
            '',
            '',
            'async def get_account_value(',
            '    account: str,',
            '    entity: str,',
            '    period: str,',
            '    year: str,',
            '    scenario: str = "Actual"',
            ') -> Optional[float]:',
            '    """Get account value for specific dimensions."""',
            '    try:',
            '        result = await smart_retrieve(',
            '            account=account,',
            '            entity=entity,',
            '            period=period,',
            '            years=year,',
            '            scenario=scenario',
            '        )',
            '        if result.get("status") == "success":',
            '            data = result.get("data", {})',
            '            rows = data.get("rows", [])',
            '            if rows and rows[0].get("data"):',
            '                value = rows[0]["data"][0]',
            '                return float(value) if value is not None else None',
            '    except Exception as e:',
            '        print(f"[ERROR] Failed to get {account} for {entity}: {e}")',
            '    return None',
            '',
            '',
            'async def collect_data() -> Dict:',
            '    """Collect data for the report."""',
            '    print("Collecting data...")',
            '    data = {}',
            '    ',
            f'    accounts = {repr(accounts)}',
            f'    entities = {repr(entities)}',
            f'    periods = {repr(periods)}',
            f'    years = {repr(years)}',
            f'    scenarios = {repr(scenarios)}',
            '    ',
            '    for account in accounts:',
            '        for entity in entities:',
            '            for period in periods:',
            '                for year in years:',
            '                    for scenario in scenarios:',
            '                        key = f"{account}|{entity}|{period}|{year}|{scenario}"',
            '                        value = await get_account_value(account, entity, period, year, scenario)',
            '                        data[key] = {',
            '                            "account": account,',
            '                            "entity": entity,',
            '                            "period": period,',
            '                            "year": year,',
            '                            "scenario": scenario,',
            '                            "value": value',
            '                        }',
            '                        if value is not None:',
            '                            print(f"[OK] {account} - {entity} - {period} {year} ({scenario}): ${value:,.2f}")',
            '    ',
            '    return data',
            '',
            '',
            'def generate_html_report(data: Dict) -> str:',
            '    """Generate HTML report."""',
            '    timestamp = datetime.now().strftime(\'%Y%m%d_%H%M%S\')',
            f'    filename = f"{script_base_name}_{{timestamp}}.html"',
            '    ',
            '    # Build HTML content',
            '    html_parts = ["""<!DOCTYPE html>',
            '<html>',
            '<head>',
            '    <meta charset="UTF-8">',
            f'    <title>{description}</title>',
            '    <style>',
            '        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }',
            '        .container { background-color: white; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }',
            '        h1 { color: #1f4788; border-bottom: 3px solid #1f4788; padding-bottom: 10px; }',
            '        h2 { color: #2c5aa0; margin-top: 30px; }',
            '        table { width: 100%; border-collapse: collapse; margin: 20px 0; }',
            '        th { background-color: #1f4788; color: white; padding: 12px; text-align: left; }',
            '        td { padding: 10px; border: 1px solid #ddd; }',
            '        tr:nth-child(even) { background-color: #f9f9f9; }',
            '        .positive { color: #2d5016; font-weight: bold; }',
            '        .negative { color: #8b0000; font-weight: bold; }',
            '        .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }',
            '    </style>',
            '</head>',
            '<body>',
            '    <div class="container">',
            f'        <h1>{description}</h1>',
            '        <p><strong>Generated:</strong> {datetime.now().strftime(\'%B %d, %Y %H:%M:%S\')}</p>',
            '        <h2>Report Data</h2>',
            '        <table>',
            '            <thead>',
            '                <tr>',
            '                    <th>Account</th>',
            '                    <th>Entity</th>',
            '                    <th>Period</th>',
            '                    <th>Year</th>',
            '                    <th>Scenario</th>',
            '                    <th style="text-align: right;">Value ($)</th>',
            '                </tr>',
            '            </thead>',
            '            <tbody>',
            '"""]',
            '    ',
            '    # Add data rows',
            '    for key, item in data.items():',
            '        value = item.get("value")',
            '        value_class = "positive" if value and value >= 0 else "negative"',
            '        value_display = f"${value:,.2f}" if value is not None else "N/A"',
            '        html_parts.append(f"""',
            '                <tr>',
            '                    <td>{item[\'account\']}</td>',
            '                    <td>{item[\'entity\']}</td>',
            '                    <td>{item[\'period\']}</td>',
            '                    <td>{item[\'year\']}</td>',
            '                    <td>{item[\'scenario\']}</td>',
            '                    <td style="text-align: right;" class="{value_class}">{value_display}</td>',
            '                </tr>',
            '""")',
            '    ',
            '    html_parts.append("""',
            '            </tbody>',
            '        </table>',
            '        <div class="footer">',
            '            <p><strong>FCCS Custom Report</strong></p>',
            '            <p>Data from Oracle EPM Cloud Financial Consolidation and Close (FCCS)</p>',
            '            <p>Generated: {datetime.now().strftime(\'%Y-%m-%d %H:%M:%S\')}</p>',
            '        </div>',
            '    </div>',
            '</body>',
            '</html>',
            '""")',
            '    ',
            '    html_content = "".join(html_parts)',
            '    ',
            '    # Save file',
            '    filepath = Path(filename)',
            '    with open(filepath, "w", encoding="utf-8") as f:',
            '        f.write(html_content)',
            '    ',
            '    return str(filepath.absolute())',
            '',
            '',
            'async def generate_report():',
            '    """Main function to generate the report."""',
            '    print("=" * 80)',
            f'    print("GENERATING {description.upper()}")',
            '    print("=" * 80)',
            '    print()',
            '    ',
            '    try:',
            '        config = load_config()',
            '        await initialize_agent(config)',
            '        print("[OK] Connected to FCCS")',
            '        print()',
            '        ',
            '        # Collect data',
            '        data = await collect_data()',
            '        print()',
            '        print(f"[OK] Collected {len(data)} data points")',
            '        print()',
            '        ',
            '        # Generate report',
            '        print("Generating report...")',
            '        report_path = generate_html_report(data)',
            '        ',
            '        print()',
            '        print("=" * 80)',
            '        print(f"[SUCCESS] Report generated: {report_path}")',
            '        print("=" * 80)',
            '        print()',
            '        ',
            '        await close_agent()',
            '        ',
            '    except Exception as e:',
            '        print(f"\\n[ERROR] {e}")',
            '        import traceback',
            '        traceback.print_exc()',
            '        sys.exit(1)',
            '',
            '',
            'if __name__ == "__main__":',
            '    asyncio.run(generate_report())',
            ''
        ]
        
        script_content = '\n'.join(script_lines)
        
        # Save script to scripts directory
        scripts_dir = Path("scripts")
        scripts_dir.mkdir(exist_ok=True)
        
        script_path = scripts_dir / script_name
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        return {
            "status": "success",
            "data": {
                "script_path": str(script_path.absolute()),
                "filename": script_name,
                "message": "Python script template generated successfully",
                "note": f"Script saved to {script_path}. Run with: python {script_path}"
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to generate script: {str(e)}"
        }
