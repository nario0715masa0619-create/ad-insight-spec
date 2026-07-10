"""
CLI Entry Point - Ad-Insight-Spec Analysis Tool

Usage:
  ad-insight-spec analyze --input /path/to/video.mp4 --lp https://example.com --output result.json
  ad-insight-spec analyze --input /path/to/image.png --mode file_only
  ad-insight-spec analyze --input /path/to/video.mp4 --lp /path/to/lp.html --kpi kpi.json --output spec.json
"""

import click
import json
import sys
import logging
from pathlib import Path
from typing import Optional

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.base_service import ProcessingError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """Ad-Insight-Spec CLI Tool"""
    pass

@cli.command()
@click.option(
    '--input', required=True, type=click.Path(exists=True),
    help='Path to creative file (video/image/text)'
)
@click.option(
    '--lp', required=False, type=str,
    help='LP URL or HTML file path'
)
@click.option(
    '--kpi', required=False, type=click.Path(exists=True),
    help='KPI JSON file path'
)
@click.option(
    '--mode', 
    type=click.Choice([
        'file_only', 
        'file_plus_lp', 
        'file_plus_lp_plus_manual_kpi', 
        'api_import_ready'
    ]),
    default='file_plus_lp_plus_manual_kpi',
    help='Input mode'
)
@click.option(
    '--output', required=False, type=click.Path(),
    default='ad_insight_spec.json',
    help='Output JSON file path'
)
def analyze(
    input: str,
    lp: Optional[str],
    kpi: Optional[str],
    mode: str,
    output: str
):
    """
    Analyze ad creative and generate diagnostic spec.
    
    Example:
      ad-insight-spec analyze --input video.mp4 --lp https://example.com --output result.json
    """
    try:
        click.echo("=" * 80)
        click.echo(f"Ad-Insight-Spec Analysis Tool")
        click.echo("=" * 80)
        click.echo(f"Input: {input}")
        if lp:
            click.echo(f"LP: {lp}")
        if kpi:
            click.echo(f"KPI: {kpi}")
        click.echo(f"Mode: {mode}")
        click.echo(f"Output: {output}")
        click.echo()
        
        # Validate input mode vs provided arguments
        _validate_mode_requirements(mode, lp, kpi)
        
        # Create orchestrator and run analysis
        logger.info(f"Starting analysis: mode={mode}")
        orchestrator = AnalysisOrchestrator(
            input_path=input,
            lp_input=lp,
            kpi_path=kpi,
            mode=mode
        )
        
        spec = orchestrator.run()
        
        # Write output
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # spec (= orchestrator.run()の戻り値) は ConverterService が
        # spec.dict()（.json()ではない）で組み立てているため、input_timestamp等の
        # datetimeフィールドは生のdatetimeオブジェクトのまま残る（既知の
        # .dict() vs .json() 落とし穴、P1で新設したasset_data/evaluation_data
        # 自体はjson.loads(model.json())経由でJSON-safe化済み）。
        #
        # default=str の設計意図（意図的なトレードオフ、PR #73レビュー指摘）:
        # ここでのdefault=strは上記の既知datetime問題に対する保険として入れたが、
        # 実装上はdatetime以外の「JSON化できない値」全般（万一の実装ミスで
        # 混入した例外オブジェクトや未対応の型など）も無条件にstr()化して
        # 書き出してしまう。つまり「想定済みの既知バグを黙って直す」と
        # 「未知のバグを黙って隠す」を区別できない。CLIはこのファイルの
        # 出力を人が目視確認する運用（自動検証なし）である前提のもと、
        # 「JSON化自体が失敗してCLIが丸ごとエラー終了する」より
        # 「多少おかしい文字列が1フィールドに混じっても出力は完了する」方を
        # 優先する意図的な選択として許容している。将来、より粒度の細かい
        # 検証（例: 既知のdatetimeフィールドだけをjson.loads(spec.json())相当で
        # 事前に正規化し、default=str自体を不要にする）に置き換える余地はある。
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2, ensure_ascii=False, default=str)
        
        click.echo()
        click.echo("=" * 80)
        click.secho(f"✅ Success! Spec saved to: {output}", fg='green')
        click.echo("=" * 80)
        
        return 0
        
    except ProcessingError as e:
        click.echo()
        click.secho(f"❌ Analysis failed: {str(e)}", fg='red', err=True)
        logger.exception("Analysis error")
        return 1
        
    except Exception as e:
        click.echo()
        click.secho(f"❌ Unexpected error: {str(e)}", fg='red', err=True)
        logger.exception("Unexpected error")
        return 1

def _validate_mode_requirements(mode: str, lp: Optional[str], kpi: Optional[str]):
    """
    Validate that mode and provided arguments are consistent.
    
    Args:
        mode: Input mode
        lp: LP input (optional)
        kpi: KPI input (optional)
        
    Raises:
        click.BadParameter: If inconsistent
    """
    if mode == 'file_only':
        if lp or kpi:
            raise click.BadParameter(
                "file_only mode does not accept --lp or --kpi"
            )
            
    elif mode == 'file_plus_lp':
        if not lp:
            raise click.BadParameter(
                "file_plus_lp mode requires --lp"
            )
        if kpi:
            raise click.BadParameter(
                "file_plus_lp mode does not accept --kpi"
            )
            
    elif mode == 'file_plus_lp_plus_manual_kpi':
        if not lp:
            raise click.BadParameter(
                "file_plus_lp_plus_manual_kpi mode requires --lp"
            )
        if not kpi:
            raise click.BadParameter(
                "file_plus_lp_plus_manual_kpi mode requires --kpi"
            )

@cli.command()
def version():
    """Show version"""
    click.echo("Ad-Insight-Spec v0.2.0 (Phase 1 - File-First Strategy)")

if __name__ == '__main__':
    sys.exit(cli())
