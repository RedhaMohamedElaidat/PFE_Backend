# data_pipeline/management/commands/sync_researcher.py

from django.core.management.base import BaseCommand
import time


class Command(BaseCommand):
    help = "Synchronise les publications depuis OpenAlex"

    def add_arguments(self, parser):
        parser.add_argument(
            "--orcid",
            type=str,
            help="ORCID du chercheur à synchroniser"
        )

        parser.add_argument(
            "--all",
            action="store_true",
            help="Synchroniser tous les chercheurs"
        )

    def handle(self, *args, **options):

        from data_pipeline.openalex_researcher_sync import (
            sync_researcher,
            sync_all_researchers
        )

        from data_pipeline.openalex_verify import validate_orcid_format # type: ignore

        start = time.time()

        # ─────────────────────────────────
        # Sync tous les chercheurs
        # ─────────────────────────────────
        if options["all"]:

            self.stdout.write(self.style.WARNING("\n🔄 Synchronisation globale...\n"))

            stats = sync_all_researchers()

            self.stdout.write(self.style.SUCCESS("\n✅ Synchronisation terminée"))
            self.stdout.write(f"Publications créées : {stats.get('created',0)}")
            self.stdout.write(f"Publications MAJ    : {stats.get('updated',0)}")
            self.stdout.write(f"Citations créées    : {stats.get('citations',0)}")
            self.stdout.write(f"Erreurs             : {stats.get('errors',0)}")

        # ─────────────────────────────────
        # Sync un chercheur
        # ─────────────────────────────────
        elif options["orcid"]:

            orcid = options["orcid"]

            self.stdout.write(f"\n🔍 Vérification ORCID : {orcid}")

            check = validate_orcid_format(orcid)

            if not check["valid"]:
                self.stdout.write(self.style.ERROR(f"❌ {check['error']}"))
                return

            profile = check["profile"]

            self.stdout.write(self.style.SUCCESS("✅ ORCID valide"))
            self.stdout.write(f"👤 Chercheur : {profile['display_name']}")
            self.stdout.write(f"🏫 Institution : {profile['institution']}")
            self.stdout.write(f"📄 Publications : {profile['works_count']}")
            self.stdout.write(f"📊 Citations : {profile['citations']}")
            self.stdout.write("")

            stats = sync_researcher(orcid)

            self.stdout.write(self.style.SUCCESS("\n✅ Synchronisation terminée"))
            self.stdout.write(f"Publications créées : {stats.get('created',0)}")
            self.stdout.write(f"Publications MAJ    : {stats.get('updated',0)}")
            self.stdout.write(f"CoAuthors créés     : {stats.get('coauthors',0)}")
            self.stdout.write(f"Citations créées    : {stats.get('citations',0)}")
            self.stdout.write(f"Erreurs             : {stats.get('errors',0)}")

        # ─────────────────────────────────
        # Mauvaise commande
        # ─────────────────────────────────
        else:

            self.stdout.write(self.style.ERROR("\n❌ Fournir --orcid ou --all\n"))

            self.stdout.write("Exemples :")
            self.stdout.write(
                "  python manage.py sync_researcher --orcid 0000-0002-1825-0097"
            )
            self.stdout.write(
                "  python manage.py sync_researcher --all"
            )

        end = time.time()

        self.stdout.write(
            self.style.WARNING(
                f"\n⏱ Temps total : {round(end - start, 2)} secondes\n"
            )
        )