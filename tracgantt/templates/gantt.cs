<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div id="ctxtnav" class="nav">
 <h2>Gantt Navigation</h2>
 <ul><li class="first"><?cs
   if:chrome.links.up.0.href ?><a href="<?cs
    var:chrome.links.up.0.href ?>">Available Charts</a><?cs
   else ?>Available Charts<?cs
  /if ?></li>
</div>

<div id="content" class="gantt">

<?cs if $gantt.id == -1 ?>
	<h1>Gantt Charts</h1>
	<p><?cs var:description ?></p>

	<table class="listing tickets">
	<thead>
	<tr>
	<?cs each col = cols ?>
		<th>
			<?cs var:col ?>
		</th>
	<?cs /each ?>
	</tr>
	</thead>

	<?cs set idx = #0 ?>
	<?cs each row = rows ?>
		<tr>
			<td><a href="<?cs var:row.href ?>">{<?cs var:row.report ?>}</a></td>
			<td><a href="<?cs var:row.href ?>"><?cs var:row.title ?></a></td>
		</tr>
	<?cs /each ?>
	</table>
	
	
<?cs else ?>
	<h1><?cs var:gantt.title ?> Gantt Chart</h1>
	

	<table class="listing tickets">
	<thead>
	<tr>
	<th/>
	<?cs each date = gantt.dates ?>
		<th>
			<?cs var:date.str ?>
		</th>
	<?cs /each ?>
	</tr>
	</thead>

	<?cs set idx = #0 ?>
	<?cs each ticket = gantt.tickets ?>
		<?cs set rcolor='color'+$ticket.color ?>

		<tr>
			<td class="ticket">
				<a title="View ticket" href="<?cs var:ticket.href ?>">
					#<?cs var:ticket.id ?></a>
			</td>
			<?cs each date = gantt.dates ?>
				<?cs if:date.ord == ticket.start ?>
					<td	class="active" colspan="<?cs var:ticket.span ?>">
						<a class="<?cs var:rcolor ?>"
								href="<?cs var:ticket.href ?>">
							#<?cs var:ticket.id ?> <?cs var:ticket.shortsum ?>
						</a>
					</td>
				<?cs elif: gantt.show_opened &&
						date.ord == ticket.open && date.ord < ticket.start ?>
					<td class="open" colspan="<?cs var:ticket.ospan ?>">
						<a class="<?cs var:rcolor ?>">
							Opened <?cs var:date.str ?>
						</a>
					</td>
				<?cs elif !gantt.show_opened && (date.ord < ticket.start || date.ord > ticket.end) ?>
					<td/>
				<?cs elif gantt.show_opened && (date.ord < ticket.open || date.ord > ticket.end) ?>
					<td/>
				<?cs /if ?>
			<?cs /each ?>
		</tr>

		<?cs set idx = idx + #1 ?>
	<?cs /each ?>
	</table>

	<?cs if $gantt.broken_no > 0 ?>	
		<p><b>WARNING</b>: The following tickets had errors that prevented them from being included in the gantt chart:</p>
		<ul>
		<?cs each ticket = gantt.broken ?>
			<li>
				<a href="<?cs var:ticket.href ?>">#<?cs var:ticket.id ?></a>
				- <?cs var:ticket.error ?>
			</li>
		<?cs /each ?>
		</ul>
	<?cs /if ?>
<?cs /if ?>
 
</div>
<?cs include "footer.cs" ?>
