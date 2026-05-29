# from django.core.management.base import BaseCommand
# from django.utils import timezone

# from announced_drills.models import CampaignRun
# from announced_drills.views import (
#     send_campaign_to_employees,
#     send_campaign_reminders
# )


# class Command(BaseCommand):
#     help = "Process scheduled cybersecurity campaigns"

#     def handle(self, *args, **kwargs):
#         now = timezone.now()

#         # 1. ENVOI DES CAMPAGNES PROGRAMMÉES
#         scheduled_campaigns = CampaignRun.objects.filter(
#             status='scheduled',
#             scheduled_at__lte=now
#         )

#         self.stdout.write(
#             self.style.WARNING(
#                 f"{scheduled_campaigns.count()} scheduled campaign(s) found."
#             )
#         )

#         for campaign in scheduled_campaigns:
#             self.stdout.write(
#                 self.style.SUCCESS(
#                     f"Sending campaign: {campaign.campaign_name}"
#                 )
#             )

#             send_campaign_to_employees(
#                 request=None,
#                 campaign=campaign
#             )

#             campaign.status = 'sent'
#             campaign.sent_at = now
#             campaign.save()

#             self.stdout.write(
#                 self.style.SUCCESS(
#                     f"Campaign sent successfully: {campaign.id}"
#                 )
#             )

#         # 2. RAPPELS AUTOMATIQUES À MI-DURÉE
#         sent_campaigns = CampaignRun.objects.filter(
#             status='sent',
#             reminder_sent_at__isnull=True,
#             expires_at__isnull=False,
#             sent_at__isnull=False
#         )

#         self.stdout.write(
#             self.style.WARNING(
#                 f"{sent_campaigns.count()} sent campaign(s) checked for reminders."
#             )
#         )

#         for campaign in sent_campaigns:
#             self.stdout.write(
#                 f"Checking campaign {campaign.id} | "
#                 f"sent_at={campaign.sent_at} | "
#                 f"expires_at={campaign.expires_at} | "
#                 f"reminder_sent_at={campaign.reminder_sent_at}"
#             )
#             print(
#                 campaign.id,
#                 campaign.campaign_name,
#                 campaign.status,
#                 campaign.sent_at,
#                 campaign.expires_at
#             )
#             total_duration = campaign.expires_at - campaign.sent_at
#             half_time = campaign.sent_at + (total_duration / 2)
#             self.stdout.write(
#                 f"now={now} | half_time={half_time}"
#             )

#             if now >= half_time:
#                 self.stdout.write(
#                     self.style.WARNING(
#                         f"Sending reminders for: {campaign.campaign_name}"
#                     )
#                 )

#                 send_campaign_reminders(campaign)

#                 campaign.reminder_sent_at = now
#                 campaign.save()

#                 self.stdout.write(
#                     self.style.SUCCESS(
#                         f"Reminder sent successfully: {campaign.id}"
#                     )
#         # =========================
#         # AUTOMATIC EXPIRATION
#         # =========================

#         expirable_campaigns = CampaignRun.objects.filter(
#             expires_at__isnull=False
#         ).exclude(
#             status='expired'
#         )

#         self.stdout.write(
#             self.style.WARNING(
#                 f"{expirable_campaigns.count()} campaign(s) checked for expiration."
#             )
#         )

#         for campaign in expirable_campaigns:

#             if now >= campaign.expires_at:

#                 campaign.status = 'expired'
#                 campaign.save()

#                 self.stdout.write(
#                     self.style.ERROR(
#                         f"Campaign expired: {campaign.id}"
#                     )
#                 )
#                 )
from django.core.management.base import BaseCommand
from django.utils import timezone

from announced_drills.models import CampaignRun
from announced_drills.views import (
    send_campaign_to_employees,
    send_campaign_reminders
)


class Command(BaseCommand):
    help = "Process scheduled cybersecurity campaigns"

    def handle(self, *args, **kwargs):
        now = timezone.now()

        # 1. ENVOI DES CAMPAGNES PROGRAMMÉES
        scheduled_campaigns = CampaignRun.objects.filter(
            status='scheduled',
            scheduled_at__lte=now
        )

        self.stdout.write(
            self.style.WARNING(
                f"{scheduled_campaigns.count()} scheduled campaign(s) found."
            )
        )

        for campaign in scheduled_campaigns:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sending campaign: {campaign.campaign_name}"
                )
            )

            send_campaign_to_employees(
                request=None,
                campaign=campaign
            )

            campaign.status = 'sent'
            campaign.sent_at = now
            campaign.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Campaign sent successfully: {campaign.id}"
                )
            )

        # 2. RAPPELS AUTOMATIQUES À MI-DURÉE
        sent_campaigns = CampaignRun.objects.filter(
            status='sent',
            reminder_sent_at__isnull=True,
            expires_at__isnull=False,
            sent_at__isnull=False
        )

        self.stdout.write(
            self.style.WARNING(
                f"{sent_campaigns.count()} sent campaign(s) checked for reminders."
            )
        )

        for campaign in sent_campaigns:
            total_duration = campaign.expires_at - campaign.sent_at
            half_time = campaign.sent_at + (total_duration / 2)

            self.stdout.write(
                f"Checking campaign {campaign.id} | "
                f"sent_at={campaign.sent_at} | "
                f"expires_at={campaign.expires_at} | "
                f"half_time={half_time} | "
                f"now={now}"
            )

            if now >= half_time:
                self.stdout.write(
                    self.style.WARNING(
                        f"Sending reminders for: {campaign.campaign_name}"
                    )
                )

                send_campaign_reminders(campaign)

                campaign.reminder_sent_at = now
                campaign.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Reminder sent successfully: {campaign.id}"
                    )
                )

        # 3. EXPIRATION AUTOMATIQUE
        expirable_campaigns = CampaignRun.objects.filter(
            expires_at__isnull=False
        ).exclude(
            status='expired'
        )

        self.stdout.write(
            self.style.WARNING(
                f"{expirable_campaigns.count()} campaign(s) checked for expiration."
            )
        )

        for campaign in expirable_campaigns:
            if now >= campaign.expires_at:
                campaign.status = 'expired'
                campaign.save()

                self.stdout.write(
                    self.style.ERROR(
                        f"Campaign expired: {campaign.id}"
                    )
                )