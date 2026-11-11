import unittest

from arch_m3.display import check_display, node_body, own_properties

GOOD = '''
/dts-v1/;
/ {
	compatible = "apple,j504", "apple,t8122", "apple,arm-platform";
	aliases {
		dcp = "/soc/dcp@28ec00000";
		dcpext = "/soc/dcp@31ac00000";
	};
	soc {
		iommu@319304000 { status = "okay"; };
		iommu@31930c000 { status = "okay"; };
		mbox@31ac08000 { status = "okay"; };
		dcp@31ac00000 {
			status = "okay";
			apple,connector-type = "DP";
			apple,dptx-phy = <0x00>;
			phy-names = "dp-phy";
			mux-control-names = "dp-xbar";
			mux-index = <0x01>;
			piodma { status = "disabled"; };
		};
		mux@70304c000 {
			compatible = "apple,t8122-display-crossbar", "apple,t6020-display-crossbar";
			status = "okay";
		};
		connector {
			displayport = <0x14>;
		};
	};
};
'''


class DisplayCheck(unittest.TestCase):
    def test_wired_tree_passes(self):
        self.assertEqual(check_display(GOOD), [])

    def test_child_properties_are_not_the_nodes_own(self):
        props = own_properties(node_body(GOOD, 'dcp@31ac00000'))
        self.assertEqual(props['status'], '"okay"')

    def test_disabled_controller_fails(self):
        bad = GOOD.replace('dcp@31ac00000 {\n\t\t\tstatus = "okay";',
                           'dcp@31ac00000 {\n\t\t\tstatus = "disabled";')
        self.assertIn('Node is not enabled: dcp@31ac00000', check_display(bad))

    def test_wrong_crossbar_input_fails(self):
        failures = check_display(GOOD.replace('mux-index = <0x01>', 'mux-index = <0x02>'))
        self.assertTrue(any('mux-index' in f for f in failures))

    def test_missing_pieces_fail(self):
        for needle in ('dcpext = "/soc/dcp@31ac00000";', 'displayport = <0x14>;',
                       'iommu@319304000 { status = "okay"; };'):
            self.assertTrue(check_display(GOOD.replace(needle, '')), needle)

    def test_other_board_fails(self):
        self.assertIn('Not a J504 device tree', check_display(GOOD.replace('apple,j504', 'apple,j514s')))


if __name__ == '__main__':
    unittest.main()
