# studio/management/commands/populate_payments.py
from pathlib import Path
from django.core.management.base import BaseCommand
from studio.utils import import_payments_from_excel

class Command(BaseCommand):
    help = "Importa pagos desde un Excel y actualiza el estado del cliente."

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_path",
            nargs="?",
            default="paquetes.xlsx",
            help="Ruta al .xlsx (relativa o absoluta)",
        )

    def handle(self, *args, **opts):
        ruta = Path(opts["excel_path"]).expanduser().resolve()
        if not ruta.exists():
            self.stderr.write(self.style.ERROR(f"Archivo no encontrado: {ruta}"))
            return

        self.stdout.write(f"Importando pagos desde: {ruta}")
        with ruta.open("rb") as fh:
            res = import_payments_from_excel(fh)

        # ‼️ Nuevo: distinguimos éxito vs. error
        if "error" in res:
            self.stderr.write(self.style.ERROR(f"✖ {res['error']}"))
            return

        # éxito
        self.stdout.write(self.style.SUCCESS(res["message"]))
        if res["errors"]:
            self.stdout.write(self.style.WARNING("Filas con problemas:"))
            for e in res["errors"]:
                self.stdout.write(f"  Fila {e['row']}: {e['error']}")