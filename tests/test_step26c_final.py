import unittest
from unittest.mock import patch
from news.weekly_chart_analysis import build_weekly_rows, weekly_chart_data, song_key


class ChartObservationMessages(unittest.TestCase):
    def row(self, spotify, youtube):
        key = song_key('QA artist', 'QA track')
        record = {'rank': 1, 'amount': 123}
        charts = [{key: [record]} if present else {} for present in (spotify, spotify, youtube, youtube)]
        with patch('news.weekly_chart_analysis.read_chart', side_effect=charts), \
             patch('news.weekly_chart_analysis._verified_tracks', return_value=({}, set())):
            return build_weekly_rows([{'artist': 'QA artist', 'track': 'QA track', 'youtube_views': 999999}])[0]

    def test_spotify_only_never_substitutes_lifetime(self):
        row = self.row(True, False)
        self.assertEqual(row['review_code'], 'partial')
        self.assertEqual(row['review_status'], 'YouTube 주간 차트에서 확인되지 않았습니다.')
        self.assertIsNone(weekly_chart_data([row])['youtube_current'][0])

    def test_youtube_only(self):
        row = self.row(False, True)
        self.assertEqual(row['review_status'], 'Spotify 주간 차트에서 확인되지 않았습니다.')
        self.assertIsNone(row['spotify_current'])

    def test_neither_observed(self):
        row = self.row(False, False)
        self.assertEqual(row['review_status'], '선택한 기간의 차트에서 확인되지 않았습니다.')
        self.assertIsNone(row['youtube_current'])

    def test_identity_review_is_distinct(self):
        row = self.row(True, True)
        self.assertEqual(row['review_code'], 'candidate')
        self.assertEqual(row['review_status'], '곡 정보 검수가 필요합니다.')


if __name__ == '__main__':
    unittest.main()
