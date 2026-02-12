package net.runelite.client.plugins.gladys;

import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.Insets;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.swing.BorderFactory;
import javax.swing.Box;
import javax.swing.BoxLayout;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingConstants;
import javax.swing.SwingUtilities;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.ui.ColorScheme;
import net.runelite.client.ui.PluginPanel;

public class GladysSensorPanel extends PluginPanel
{
	private static final Color GREEN = new Color(0, 200, 83);
	private static final Color DIM = new Color(150, 150, 150);
	private static final float FONT_SM = 13f;
	private static final float FONT_LG = 16f;
	private static final float FONT_TITLE = 18f;

	private static final String[] EVENT_TYPES = {
		"spawn_despawn", "movement", "damage", "stat_change",
		"action_state", "menu_action", "item_change", "chat",
		"session_state", "sound", "misc"
	};

	private static final String[] EVENT_LABELS = {
		"Spawn/Despawn", "Movement", "Damage", "Stat Change",
		"Action State", "Menu Action", "Item Change", "Chat",
		"Session State", "Sound", "Misc"
	};

	// Config keys matching GladysSensorConfig method names
	private static final String[] CONFIG_KEYS = {
		"spawnDespawn", "movement", "damage", "statChange",
		"actionState", "menuAction", "itemChange", "chat",
		"sessionState", "sound", "misc"
	};

	private static final boolean[] DEFAULT_ENABLED = {
		true, true, true, true,
		true, true, true, true,
		true, false, false
	};

	private final Map<String, JLabel> countLabels = new LinkedHashMap<>();
	private final Map<String, JCheckBox> toggleBoxes = new LinkedHashMap<>();
	private GladysSensorPlugin plugin;

	public GladysSensorPanel()
	{
		// Defer layout until init() is called with plugin reference
	}

	public void init(GladysSensorPlugin plugin)
	{
		this.plugin = plugin;
		buildPanel();
	}

	private void buildPanel()
	{
		removeAll();
		setLayout(new BoxLayout(this, BoxLayout.Y_AXIS));
		setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));
		setBackground(ColorScheme.DARK_GRAY_COLOR);

		ConfigManager cm = plugin.getConfigManager();

		// ── Header ──────────────────────────────────────────────
		JPanel header = new JPanel(new BorderLayout());
		header.setBackground(ColorScheme.DARKER_GRAY_COLOR);
		header.setBorder(BorderFactory.createEmptyBorder(14, 10, 14, 10));
		header.setMaximumSize(new Dimension(Integer.MAX_VALUE, 70));

		JLabel title = new JLabel("GLADyS Sensor", SwingConstants.CENTER);
		title.setForeground(Color.WHITE);
		title.setFont(title.getFont().deriveFont(Font.BOLD, FONT_TITLE));

		JLabel status = new JLabel("Active", SwingConstants.CENTER);
		status.setForeground(GREEN);
		status.setFont(status.getFont().deriveFont(Font.PLAIN, FONT_SM));
		status.setBorder(BorderFactory.createEmptyBorder(4, 0, 0, 0));

		header.add(title, BorderLayout.NORTH);
		header.add(status, BorderLayout.CENTER);
		add(header);

		add(Box.createRigidArea(new Dimension(0, 10)));

		// ── Log to Chat toggle ──────────────────────────────────
		JCheckBox chatToggle = new JCheckBox("Log to Chat");
		chatToggle.setSelected(false);
		chatToggle.setBackground(ColorScheme.DARK_GRAY_COLOR);
		chatToggle.setForeground(Color.WHITE);
		chatToggle.setFont(chatToggle.getFont().deriveFont(Font.BOLD, FONT_SM));
		chatToggle.setAlignmentX(LEFT_ALIGNMENT);
		chatToggle.addActionListener(e -> plugin.setLogToChat(chatToggle.isSelected()));
		add(chatToggle);

		add(Box.createRigidArea(new Dimension(0, 10)));

		// ── Connection Status ──────────────────────────────────
		JLabel connTitle = new JLabel("Orchestrator");
		connTitle.setForeground(DIM);
		connTitle.setFont(connTitle.getFont().deriveFont(Font.BOLD, FONT_SM));
		connTitle.setAlignmentX(LEFT_ALIGNMENT);
		connTitle.setBorder(BorderFactory.createEmptyBorder(0, 2, 4, 0));
		add(connTitle);

		String host = cm.getConfiguration("gladys", "orchestratorHost");
		String port = cm.getConfiguration("gladys", "orchestratorPort");
		if (host == null || host.isEmpty()) host = "localhost";
		if (port == null || port.isEmpty()) port = "50051";

		JLabel connLabel = new JLabel(host + ":" + port);
		connLabel.setForeground(GREEN);
		connLabel.setFont(connLabel.getFont().deriveFont(Font.PLAIN, FONT_SM));
		connLabel.setAlignmentX(LEFT_ALIGNMENT);
		connLabel.setBorder(BorderFactory.createEmptyBorder(0, 2, 0, 0));
		add(connLabel);

		add(Box.createRigidArea(new Dimension(0, 10)));

		// ── Event rows: toggle + label + count ──────────────────
		JLabel sectionTitle = new JLabel("Event Categories");
		sectionTitle.setForeground(DIM);
		sectionTitle.setFont(sectionTitle.getFont().deriveFont(Font.BOLD, FONT_SM));
		sectionTitle.setAlignmentX(LEFT_ALIGNMENT);
		sectionTitle.setBorder(BorderFactory.createEmptyBorder(0, 2, 6, 0));
		add(sectionTitle);

		JPanel grid = new JPanel(new GridBagLayout());
		grid.setBackground(ColorScheme.DARKER_GRAY_COLOR);
		grid.setBorder(BorderFactory.createEmptyBorder(8, 6, 8, 8));
		grid.setMaximumSize(new Dimension(Integer.MAX_VALUE, EVENT_TYPES.length * 28 + 16));

		GridBagConstraints gbc = new GridBagConstraints();
		gbc.gridy = 0;
		gbc.insets = new Insets(1, 0, 1, 0);

		for (int i = 0; i < EVENT_TYPES.length; i++)
		{
			final int idx = i;

			// Checkbox
			JCheckBox cb = new JCheckBox();
			boolean enabled = getConfigBool(cm, CONFIG_KEYS[i], DEFAULT_ENABLED[i]);
			cb.setSelected(enabled);
			cb.setBackground(ColorScheme.DARKER_GRAY_COLOR);
			cb.addActionListener(e ->
				cm.setConfiguration("gladys", CONFIG_KEYS[idx], cb.isSelected()));
			toggleBoxes.put(EVENT_TYPES[i], cb);

			gbc.gridx = 0;
			gbc.weightx = 0;
			gbc.fill = GridBagConstraints.NONE;
			gbc.anchor = GridBagConstraints.WEST;
			grid.add(cb, gbc);

			// Label
			JLabel nameLabel = new JLabel(EVENT_LABELS[i]);
			nameLabel.setForeground(enabled ? Color.WHITE : DIM);
			nameLabel.setFont(nameLabel.getFont().deriveFont(Font.PLAIN, FONT_SM));

			gbc.gridx = 1;
			gbc.weightx = 1.0;
			gbc.fill = GridBagConstraints.HORIZONTAL;
			grid.add(nameLabel, gbc);

			// Count
			JLabel countLabel = new JLabel("0", SwingConstants.RIGHT);
			countLabel.setForeground(Color.WHITE);
			countLabel.setFont(countLabel.getFont().deriveFont(Font.PLAIN, FONT_SM));

			gbc.gridx = 2;
			gbc.weightx = 0;
			gbc.fill = GridBagConstraints.NONE;
			gbc.anchor = GridBagConstraints.EAST;
			gbc.insets = new Insets(1, 8, 1, 0);
			grid.add(countLabel, gbc);
			gbc.insets = new Insets(1, 0, 1, 0);

			countLabels.put(EVENT_TYPES[i], countLabel);

			// Update label color when toggled
			cb.addActionListener(e ->
				nameLabel.setForeground(cb.isSelected() ? Color.WHITE : DIM));

			gbc.gridy++;
		}

		add(grid);

		add(Box.createRigidArea(new Dimension(0, 10)));

		// ── Total ───────────────────────────────────────────────
		JPanel totalPanel = new JPanel(new BorderLayout());
		totalPanel.setBackground(ColorScheme.DARKER_GRAY_COLOR);
		totalPanel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		totalPanel.setMaximumSize(new Dimension(Integer.MAX_VALUE, 36));

		JLabel totalLabel = new JLabel("Total");
		totalLabel.setForeground(Color.WHITE);
		totalLabel.setFont(totalLabel.getFont().deriveFont(Font.BOLD, FONT_LG));

		JLabel totalCount = new JLabel("0", SwingConstants.RIGHT);
		totalCount.setForeground(GREEN);
		totalCount.setFont(totalCount.getFont().deriveFont(Font.BOLD, FONT_LG));
		countLabels.put("_total", totalCount);

		totalPanel.add(totalLabel, BorderLayout.WEST);
		totalPanel.add(totalCount, BorderLayout.EAST);
		add(totalPanel);

		add(Box.createRigidArea(new Dimension(0, 10)));

		// ── Reset button ────────────────────────────────────────
		JButton resetButton = new JButton("Reset Counts");
		resetButton.setFont(resetButton.getFont().deriveFont(Font.PLAIN, FONT_SM));
		resetButton.setMaximumSize(new Dimension(Integer.MAX_VALUE, 32));
		resetButton.addActionListener(e ->
		{
			plugin.getEventCounts().clear();
			updateCounts();
		});
		add(resetButton);

		revalidate();
		repaint();
	}

	private boolean getConfigBool(ConfigManager cm, String key, boolean defaultVal)
	{
		String val = cm.getConfiguration("gladys", key);
		if (val == null) return defaultVal;
		return Boolean.parseBoolean(val);
	}

	public void updateCounts()
	{
		SwingUtilities.invokeLater(() ->
		{
			if (plugin == null) return;

			Map<String, Integer> counts = plugin.getEventCounts();
			int total = 0;

			for (String type : EVENT_TYPES)
			{
				int count = counts.getOrDefault(type, 0);
				total += count;
				JLabel label = countLabels.get(type);
				if (label != null)
				{
					label.setText(String.valueOf(count));
					label.setForeground(count > 0 ? Color.WHITE : DIM);
				}
			}

			JLabel totalLabel = countLabels.get("_total");
			if (totalLabel != null)
			{
				totalLabel.setText(String.valueOf(total));
			}
		});
	}

}
